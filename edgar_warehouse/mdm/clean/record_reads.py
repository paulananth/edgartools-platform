"""Transport Rust's affected-record requests through the existing storage adapter."""

from __future__ import annotations

import json

from edgar_warehouse.rules.source_engine import plan_affected_records

from .store import Conflict


def read_affected_records(
    adapter, assertions: list[dict], decisions: list[dict], *, connection=None
) -> dict:
    """Read indexed inputs; the returned generation must guard their later save.

    Rust owns the scope and traversal. Python only transports its grouped read
    requests and validates stored reference envelopes. The owning save must
    enforce the observed generation before committing its prepared effects.
    """
    if adapter.protocol < 3:
        raise Conflict("Affected-record reads require indexed lookup storage")
    generation = adapter.generation(connection=connection)
    reader = RecordReader(adapter, connection=connection)
    readings, retained_decisions, identities = {}, {}, {}
    completed_lookups, completed_identities = set(), set()
    while True:
        try:
            plan = plan_affected_records(
                {
                    "assertions": assertions,
                    "decisions": decisions,
                    "retained_readings": list(readings.values()),
                    "retained_decisions": list(retained_decisions.values()),
                    "completed_lookups": sorted(completed_lookups),
                    "completed_identities": sorted(completed_identities),
                }
            )
        except ValueError as error:
            raise Conflict(str(error)) from None
        if plan["ready"]:
            return {
                "generation": generation,
                "readings": readings,
                "decisions": retained_decisions,
                "identities": list(identities.values()),
                "subjects": set(plan["subjects"]),
            }
        before = len(completed_lookups) + len(completed_identities)
        for (record_type, record_id), body in reader.retained_groups(
            plan["lookups"]
        ).items():
            (readings if record_type == "source-reading" else retained_decisions)[
                record_id
            ] = body
        completed_lookups.update(plan["lookups"])
        identity_keys = [("identity", record_id) for record_id in plan["identities"]]
        for (_, record_id), body in reader.inputs(
            identity_keys, required=False
        ).items():
            identities[record_id] = body
        completed_identities.update(plan["identities"])
        if len(completed_lookups) + len(completed_identities) == before:
            raise Conflict("Affected-record reads made no progress")


class RecordReader:
    """Indexed transport of retained inputs and current source-record pointers.

    The shared native engine prepares these references in the owning save.
    Reads use that same destination connection and never infer a newer pin.
    """

    def __init__(self, adapter, *, connection=None, routes=None):
        if adapter.protocol < 3:
            raise Conflict("Record reads require indexed lookup storage")
        self.adapter = adapter
        self.connection = connection
        self.routes = (
            None
            if routes is None
            else {name: tuple(path) for name, path in routes.items()}
        )

    @staticmethod
    def group(name: str, *keys: str) -> str:
        from .store import canonical

        return "lookup/" + name + "/" + canonical(list(keys))

    @staticmethod
    def _body(entry):
        try:
            body = json.loads(entry["body"])
        except (ValueError, TypeError):
            raise Conflict("Invalid retained record body") from None
        if not isinstance(body, dict):
            raise Conflict("Invalid retained record body")
        return body

    def inputs(self, keys, *, required=True):
        """Read exact immutable keys; a dangling pointer is never an empty result."""
        wanted = set(keys)
        found = self.adapter.read(
            sorted(wanted), immutable=True, connection=self.connection
        )
        if required and set(found) != wanted:
            raise Conflict("Retained-input reference has no saved input")
        result = {}
        fields = {
            "source-reading": "assertion_id",
            "decision": "decision_id",
            "identity": "entity_id",
        }
        for (kind, key), entry in found.items():
            body = self._body(entry)
            if kind not in fields or body.get(fields[kind]) != key:
                raise Conflict("Retained-input identity differs from its stored key")
            if kind == "source-reading":
                from .evidence import validate_assertion

                validate_assertion(body)
            elif kind == "decision":
                from .store import digest

                if digest({k: v for k, v in body.items() if k != "decision_id"}) != key:
                    raise Conflict("Retained decision hash differs from its body")
            result[kind, key] = body
        return result

    def subjects(self, groups):
        """Resolve current-member pointers, rejecting a mismatched member key."""
        return {member for _, member in self.subject_entries(groups)}

    def subject_entries(self, groups):
        found = self.adapter.read_lookup_groups(
            sorted(set(groups)), connection=self.connection
        )
        for (_group, member), entry in found.items():
            body = self._body(entry)
            if set(body) != {"subject"} or body["subject"] != member:
                raise Conflict("Invalid source-record pointer")
        return found

    def current(self, subjects):
        wanted = {("source-record", subject) for subject in subjects}
        found = self.adapter.read(
            sorted(wanted), lookup=True, connection=self.connection
        )
        result = {}
        for (_kind, subject), entry in found.items():
            body = self._body(entry)
            if (
                body.get("subject") != subject
                or not isinstance(body.get("assertion_id"), str)
                or not body["assertion_id"]
            ):
                raise Conflict("Current source-record identity differs from its key")
            result[subject] = body
        return result

    def bindings(self, subjects):
        """Read stored bindings only after validating current reading provenance."""
        pointers = self.current(subjects)
        self._readings(pointers)
        return {
            subject: body["entity_id"]
            for subject, body in pointers.items()
            if body.get("entity_id")
        }

    def readings(self, subjects):
        pointers = self.current(subjects)
        return self._readings(pointers)

    def _readings(self, pointers):
        found = self.inputs(
            ("source-reading", pointer["assertion_id"]) for pointer in pointers.values()
        )
        result = {}
        for subject, pointer in pointers.items():
            body = found["source-reading", pointer["assertion_id"]]
            if body.get("subject") != subject:
                raise Conflict("Current source-record pointer names another subject")
            for field in (
                "source_code",
                "record_key",
                "kind",
                "revision",
                "publication_key",
                "effective_at",
            ):
                if pointer.get(field) != body.get(field):
                    raise Conflict(
                        "Current source-record pointer differs from retained reading"
                    )
            if pointer.get("mapping_version", 1) != body.get("mapping_version", 1):
                raise Conflict(
                    "Current source-record mapping differs from retained reading"
                )
            for field in ("identifiers", "cross_references"):
                if (pointer.get(field) or {}) != (body.get(field) or {}):
                    raise Conflict(
                        "Current source-record identifiers differ from retained reading"
                    )
            result[subject] = body
        return result

    def members(self, identities):
        identities = set(identities)
        entries = self.subject_entries(
            self.group("master_members", identity) for identity in identities
        )
        subjects = {member for _, member in entries}
        pointers = self.current(subjects)
        if set(pointers) != subjects or any(
            pointers[member].get("entity_id") != self._group(group)[1]
            for group, member in entries
        ):
            raise Conflict("Master membership differs from current source records")
        self._readings(pointers)
        return subjects

    def candidates(self, source, route, values):
        from .matching import candidate_value
        from .store import digest

        routes = {route} if isinstance(route, str) else set(route)
        if self.routes is None or not routes or not routes <= set(self.routes):
            raise Conflict("Candidate reads require a declared frozen route")
        values = set(values)
        entries = self.subject_entries(
            self.group("name_candidates", source, name, value)
            for name in sorted(routes)
            for value in sorted(values)
        )
        subjects = {member for _, member in entries}
        pointers = self.current(subjects)
        if set(pointers) != subjects:
            raise Conflict("Candidate reference has no current source record")
        expected = digest(self.routes)
        if any(
            pointer.get("matching_routes_sha256") != expected
            for pointer in pointers.values()
        ):
            raise Conflict(
                "Candidate routes changed without reindexing current readings"
            )
        records = self._readings(pointers)
        for group, member in entries:
            _, keys = self._group_keys(group, 3)
            indexed_source, name, value = keys
            if (
                records[member].get("source_code") != indexed_source
                or candidate_value(records[member], self.routes[name]) != value
            ):
                raise Conflict("Candidate reference differs from its retained reading")
        return list(records.values())

    def masters(self, identities):
        found = self.adapter.read(
            [("entity", identity) for identity in sorted(set(identities))],
            connection=self.connection,
        )
        result = {}
        for (_kind, identity), entry in found.items():
            body = self._body(entry)
            if body.get("entity_id") != identity:
                raise Conflict("Saved master identity differs from its key")
            result[identity] = body
        return result

    def related_decisions(self, keys):
        return list(
            self.retained_groups(
                self.group("related_decisions", key) for key in sorted(set(keys))
            ).values()
        )

    @staticmethod
    def _group_keys(group, size):
        try:
            prefix, name, raw = group.split("/", 2)
            keys = json.loads(raw)
        except (ValueError, TypeError):
            raise Conflict("Invalid record lookup group") from None
        if (
            prefix != "lookup"
            or not isinstance(keys, list)
            or len(keys) != size
            or any(not isinstance(key, str) for key in keys)
        ):
            raise Conflict("Invalid record lookup group")
        return name, keys

    @classmethod
    def _group(cls, group):
        name, keys = cls._group_keys(group, 1)
        return name, keys[0]

    def retained_groups(self, groups):
        entries = self.adapter.read_lookup_groups(
            sorted(set(groups)), connection=self.connection
        )
        wanted = set()
        for (group, member), entry in entries.items():
            family, _ = self._group(group)
            kind = {
                "record_readings": "source-reading",
                "source_readings": "source-reading",
                "related_readings": "source-reading",
                "related_decisions": "decision",
                "source_retirements": "decision",
            }.get(family)
            if kind is None or self._body(entry) != {
                "type": kind,
                "id": member,
                "immutable": True,
            }:
                raise Conflict("Invalid retained-input reference")
            wanted.add((kind, member))
        found = self.inputs(wanted)
        from .scope import anchors, link_ends

        for (group, member), entry in entries.items():
            family, key = self._group(group)
            kind = self._body(entry)["type"]
            body = found[kind, member]
            matches = (
                body.get("subject") == key
                if family == "record_readings"
                else body.get("source_code") == key
                if family == "source_readings"
                else key in anchors(body)
                if family == "related_decisions"
                else body.get("operation") == "retire_source"
                and body.get("source_code") == key
                if family == "source_retirements"
                else any(key in (start, target) for _, start, target in link_ends(body))
            )
            if not matches:
                raise Conflict(
                    "Retained-input reference lies outside its indexed scope"
                )
        return found

    def holders(self, namespace, values, sources, released=()):
        """Read issuing records by normalized identifier and verify their authority."""
        wanted = {(source, value) for source in sources for value in values}
        entries = self.subject_entries(
            self.group("identifier_records", namespace, value, source, "bound")
            for source, value in sorted(wanted)
        )
        subjects = {member for _, member in entries} - set(released)
        pointers = self.current(subjects)
        if set(pointers) != subjects:
            raise Conflict("Identifier reference has no current source record")
        readings = self._readings(pointers)
        identities = self.inputs(
            ("identity", pointer["entity_id"])
            for pointer in pointers.values()
            if pointer.get("entity_id")
        )
        if any(
            not pointer.get("entity_id")
            or (
                pointer.get("source_code"),
                (pointer.get("normalized_identifiers") or {}).get(namespace),
            )
            not in wanted
            for pointer in pointers.values()
        ):
            raise Conflict("Identifier reference differs from current source record")
        for group, member in entries:
            if member not in subjects:
                continue
            _, keys = self._group_keys(group, 4)
            name, value, source, state = keys
            pointer = pointers[member]
            if (
                pointer.get("source_code") != source
                or not pointer.get("entity_id")
                or state != "bound"
                or (pointer.get("normalized_identifiers") or {}).get(name) != value
                or not isinstance(
                    (readings[member].get("identifiers") or {}).get(name), str
                )
            ):
                raise Conflict("Identifier reference differs from its indexed scope")
        return [
            {
                "value": (record.get("identifiers") or {}).get(namespace),
                "entity_id": pointers[subject]["entity_id"],
                "kind": identities["identity", pointers[subject]["entity_id"]]["kind"],
            }
            for subject, record in readings.items()
        ]

    def newest(self, kinds):
        """Publication floors are single keyed records, never a scan of a kind."""
        from .evidence import instant

        wanted = {("identity-publication", kind) for kind in kinds}
        found = self.adapter.read(
            sorted(wanted), lookup=True, connection=self.connection
        )
        result = {kind: None for kind in kinds}
        for (_, kind), entry in found.items():
            body = self._body(entry)
            if (
                set(body) != {"entity_id", "kind", "published_at"}
                or body["kind"] != kind
            ):
                raise Conflict("Invalid identity publication reference")
            identity = self.inputs([("identity", body["entity_id"])])[
                "identity", body["entity_id"]
            ]
            if identity.get("kind") != kind or instant(
                identity["published_at"]
            ) != instant(body["published_at"]):
                raise Conflict("Identity publication differs from retained identity")
            result[kind] = body["published_at"]
        return result

    def source_readings(self, subjects=(), assertion_ids=()):
        groups = [
            self.group("record_readings", subject) for subject in sorted(set(subjects))
        ]
        found = self.retained_groups(groups)
        found.update(self.inputs(("source-reading", key) for key in assertion_ids))
        return list(found.values())

    def projections(self, *, starts=(), changed=(), reviews=()):
        groups = {
            self.group(family, key)
            for family, keys in (
                ("outgoing_links", starts),
                ("incoming_links", changed),
                ("related_reviews", reviews),
            )
            for key in keys
        }
        entries = self.adapter.read_lookup_groups(
            sorted(groups), connection=self.connection
        )
        wanted = set()
        for (group, member), entry in entries.items():
            family, _ = self._group(group)
            kind = "review" if family == "related_reviews" else "relationship"
            if self._body(entry) != {"type": kind, "id": member, "immutable": False}:
                raise Conflict("Invalid current projection reference")
            wanted.add((kind, member))
        saved = self.adapter.read(sorted(wanted), connection=self.connection)
        if set(saved) != wanted:
            raise Conflict("Current projection reference has no saved object")
        found = {}
        for (kind, key), entry in saved.items():
            body = self._body(entry)
            if body.get("review_id" if kind == "review" else "relationship_id") != key:
                raise Conflict("Current projection identity differs from its key")
            if kind == "relationship" and (
                any(
                    not isinstance(body.get(field), str) or not body[field]
                    for field in ("source_id", "target_id", "type")
                )
                or "retired" in body
                and type(body["retired"]) is not bool
            ):
                raise Conflict("Invalid current relationship projection")
            found[kind, key] = body
        for (group, member), entry in entries.items():
            family, key = self._group(group)
            body = found[self._body(entry)["type"], member]
            matches = (
                body.get("source_id") == key
                if family == "outgoing_links"
                else body.get("target_id") == key
                if family == "incoming_links"
                else key
                in {
                    body.get("entity_id"),
                    body.get("subject"),
                    *body.get("affected_subjects", []),
                    *body.get("entities", []),
                }
            )
            if not matches:
                raise Conflict(
                    "Current projection reference lies outside its indexed scope"
                )
        return [
            {"object_type": kind, "object_id": key, "body": body}
            for (kind, key), body in found.items()
        ]


def for_connection(conn):
    """Select the qualified read contract; the normal write gate stays separate."""
    if conn.dialect.name == "postgresql":
        return conn
    if conn.dialect.name != "mysql":
        raise Conflict("Normal MDM reads are qualified for PostgreSQL and MySQL only")
    from . import catalog, matching
    from .store import digest, storage_adapter

    catalog.assert_current()
    api = storage_adapter()
    api.require_registry(conn, digest(catalog.CATALOG))
    return RecordReader(
        api.Adapter(conn.engine, prefix="mdm_store", protocol=4),
        connection=conn,
        routes=matching.candidate_routes(),
    )

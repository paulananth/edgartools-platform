"""Transport Rust's affected-record requests through the existing storage adapter."""

from __future__ import annotations

import json

from edgar_warehouse.rules.source_engine import plan_affected_records

from .store import Conflict


def read_affected_records(adapter, assertions: list[dict], decisions: list[dict], *, connection=None) -> dict:
    """Read indexed inputs; the returned generation must guard their later save.

    Rust owns the scope and traversal. Python only transports its grouped read
    requests and validates stored reference envelopes. This does not qualify
    the remaining relationship scope or the normal selected-engine caller.
    """
    if adapter.protocol < 3:
        raise Conflict("Affected-record reads require indexed lookup storage")
    generation = adapter.generation(connection=connection)
    reader = RecordReader(adapter, connection=connection)
    readings, retained_decisions, identities = {}, {}, {}
    completed_lookups, completed_identities = set(), set()
    while True:
        try:
            plan = plan_affected_records({
                "assertions": assertions, "decisions": decisions,
                "retained_readings": list(readings.values()),
                "retained_decisions": list(retained_decisions.values()),
                "completed_lookups": sorted(completed_lookups),
                "completed_identities": sorted(completed_identities),
            })
        except ValueError as error:
            raise Conflict(str(error)) from None
        if plan["ready"]:
            return {
                "generation": generation, "readings": readings,
                "decisions": retained_decisions, "identities": list(identities.values()),
                "subjects": set(plan["subjects"]),
            }
        before = len(completed_lookups) + len(completed_identities)
        groups = adapter.read_lookup_groups(plan["lookups"], connection=connection)
        requested = set()
        for entry in groups.values():
            try:
                reference = json.loads(entry["body"])
            except (ValueError, TypeError):
                raise Conflict("Invalid retained-input reference") from None
            if (not isinstance(reference, dict) or set(reference) != {"type", "id", "immutable"}
                    or reference["immutable"] is not True
                    or not isinstance(reference["type"], str)
                    or reference["type"] not in {"source-reading", "decision"}
                    or not isinstance(reference["id"], str) or not reference["id"]):
                raise Conflict("Invalid retained-input reference")
            requested.add((reference["type"], reference["id"]))
        requested = {key for key in requested if key[1] not in (
            readings if key[0] == "source-reading" else retained_decisions
        )}
        for (record_type, record_id), body in reader.inputs(requested).items():
            (readings if record_type == "source-reading" else retained_decisions)[record_id] = body
        completed_lookups.update(plan["lookups"])
        identity_keys = [("identity", record_id) for record_id in plan["identities"]]
        for (_, record_id), body in reader.inputs(identity_keys, required=False).items():
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
        self.routes = None if routes is None else {name:tuple(path) for name,path in routes.items()}

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
        found = self.adapter.read(sorted(wanted), immutable=True, connection=self.connection)
        if required and set(found) != wanted:
            raise Conflict("Retained-input reference has no saved input")
        result = {}
        fields = {"source-reading":"assertion_id", "decision":"decision_id", "identity":"entity_id"}
        for (kind, key), entry in found.items():
            body = self._body(entry)
            if kind not in fields or body.get(fields[kind]) != key:
                raise Conflict("Retained-input identity differs from its stored key")
            result[kind,key] = body
        return result

    def subjects(self, groups):
        """Resolve current-member pointers, rejecting a mismatched member key."""
        found = self.adapter.read_lookup_groups(sorted(set(groups)), connection=self.connection)
        subjects = set()
        for (_group, member), entry in found.items():
            body = self._body(entry)
            if set(body) != {"subject"} or body["subject"] != member:
                raise Conflict("Invalid source-record pointer")
            subjects.add(member)
        return subjects

    def current(self, subjects):
        wanted = {("source-record", subject) for subject in subjects}
        found = self.adapter.read(sorted(wanted), lookup=True, connection=self.connection)
        result = {}
        for (_kind, subject), entry in found.items():
            body = self._body(entry)
            if (body.get("subject") != subject or not isinstance(body.get("assertion_id"), str)
                    or not body["assertion_id"]):
                raise Conflict("Current source-record identity differs from its key")
            result[subject] = body
        return result

    def readings(self, subjects):
        pointers = self.current(subjects)
        return self._readings(pointers)

    def _readings(self, pointers):
        found = self.inputs(("source-reading", pointer["assertion_id"]) for pointer in pointers.values())
        result = {}
        for subject, pointer in pointers.items():
            body = found["source-reading",pointer["assertion_id"]]
            if body.get("subject") != subject:
                raise Conflict("Current source-record pointer names another subject")
            for field in ("source_code", "record_key", "kind", "revision", "publication_key", "effective_at"):
                if pointer.get(field) != body.get(field):
                    raise Conflict("Current source-record pointer differs from retained reading")
            if pointer.get("mapping_version",1) != body.get("mapping_version",1):
                raise Conflict("Current source-record mapping differs from retained reading")
            for field in ("identifiers", "cross_references"):
                if (pointer.get(field) or {}) != (body.get(field) or {}):
                    raise Conflict("Current source-record identifiers differ from retained reading")
            result[subject] = body
        return result

    def members(self, identities):
        identities = set(identities)
        subjects = self.subjects(self.group("master_members", identity) for identity in identities)
        pointers = self.current(subjects)
        if set(pointers) != subjects or any(pointer.get("entity_id") not in identities for pointer in pointers.values()):
            raise Conflict("Master membership differs from current source records")
        return subjects

    def candidates(self, source, route, values):
        from .matching import candidate_value
        from .store import digest
        routes = {route} if isinstance(route,str) else set(route)
        if self.routes is None or not routes or not routes <= set(self.routes):
            raise Conflict("Candidate reads require a declared frozen route")
        values = set(values)
        subjects = self.subjects(self.group("name_candidates",source,name,value)
                                 for name in sorted(routes) for value in sorted(values))
        pointers = self.current(subjects)
        if set(pointers) != subjects:
            raise Conflict("Candidate reference has no current source record")
        expected = digest(self.routes)
        if any(pointer.get("matching_routes_sha256") != expected for pointer in pointers.values()):
            raise Conflict("Candidate routes changed without reindexing current readings")
        records = self._readings(pointers)
        if any(record.get("source_code") != source or not any(candidate_value(record,self.routes[name]) in values for name in routes)
               for record in records.values()):
            raise Conflict("Candidate reference differs from its retained reading")
        return list(records.values())

    def masters(self, identities):
        found = self.adapter.read([("entity", identity) for identity in sorted(set(identities))],
                                  connection=self.connection)
        result = {}
        for (_kind, identity), entry in found.items():
            body = self._body(entry)
            if body.get("entity_id") != identity:
                raise Conflict("Saved master identity differs from its key")
            result[identity] = body
        return result

    def related_decisions(self, keys):
        entries = self.adapter.read_lookup_groups(
            [self.group("related_decisions", key) for key in sorted(set(keys))], connection=self.connection)
        wanted = set()
        for (_group, key), entry in entries.items():
            pointer = self._body(entry)
            if pointer != {"type":"decision","id":key,"immutable":True}:
                raise Conflict("Invalid retained decision reference")
            wanted.add(("decision", key))
        return list(self.inputs(wanted).values())

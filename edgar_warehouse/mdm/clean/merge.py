"""One bounded, atomic Merge Stage for all Clean MDM writers.

The retained decision graph supplies identity; source policy supplies fields.
Neither auto binding nor automatic consolidation is enabled in this release.
"""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import assessment, relationships
from .evidence import instant, validate_assertion, validate_deferred
from .identity import replay
from .store import Conflict, Store, canonical, digest, rows
from .survivorship import current_claims, select_fields


def anchors(decision: dict) -> set[str]:
    return {
        str(decision[k])
        for k in ("subject", "entity_id", "left", "right", "target", "decision_id")
        if decision.get(k)
    }


def load_closure(conn, assertions: list[dict], decisions: list[dict], *, limit: int):
    """Conservative closure includes historical merges and incoming/outgoing edges.

    Every query is bounded. A component over the budget is rejected before any
    writes, so operators can plan an isolated-generation rebuild instead.
    """
    keys = {a["subject"] for a in assertions} | {
        k for d in decisions for k in anchors(d)
    }
    for a in assertions:
        keys.update(
            r["target_subject"] for r in a["relationships"] if r.get("target_subject")
        )
    stored_a = {}
    stored_d = {}
    retiring = [
        d["source_code"] for d in decisions if d["operation"] == "retire_source"
    ]
    while keys:
        before = set(keys)
        evidence = rows(
            conn,
            """SELECT body FROM mdm_v2.assertion
            WHERE source_code=ANY(:retiring) OR body->>'subject'=ANY(:keys) OR EXISTS(
             SELECT 1 FROM jsonb_array_elements(body->'relationships') r WHERE r->>'target_subject'=ANY(:keys)) LIMIT :lim""",
            keys=sorted(keys),
            retiring=retiring,
            lim=limit + 1,
        )
        decision_rows = rows(
            conn,
            """SELECT body FROM mdm_v2.decision WHERE
            body->>'subject'=ANY(:keys) OR body->>'entity_id'=ANY(:keys) OR body->>'left'=ANY(:keys)
            OR body->>'right'=ANY(:keys) OR body->>'target'=ANY(:keys) OR decision_id=ANY(:keys) LIMIT :lim""",
            keys=sorted(keys),
            lim=limit + 1,
        )
        for r in evidence:
            a = r["body"]
            stored_a[a["assertion_id"]] = a
            keys.add(a["subject"])
            keys.update(
                e["target_subject"]
                for e in a["relationships"]
                if e.get("target_subject")
            )
        for r in decision_rows:
            d = r["body"]
            stored_d[d["decision_id"]] = d
            keys.update(anchors(d))
        if len(stored_a) + len(stored_d) > limit:
            raise Conflict("Affected closure exceeds bounded replay budget")
        if keys == before:
            break
    sources = sorted({a["source_code"] for a in [*stored_a.values(), *assertions]})
    for r in rows(
        conn,
        "SELECT body FROM mdm_v2.decision WHERE operation='retire_source' AND body->>'source_code'=ANY(:sources) LIMIT :lim",
        sources=sources,
        lim=limit + 1,
    ):
        stored_d[r["body"]["decision_id"]] = r["body"]
    id_keys = []
    for key in keys:
        try:
            id_keys.append(str(UUID(key)))
        except ValueError:
            pass
    identities = rows(
        conn,
        "SELECT entity_id::text,kind,published_at::text FROM mdm_v2.identity WHERE entity_id::text=ANY(:keys) LIMIT :lim",
        keys=id_keys,
        lim=limit + 1,
    )
    if len(identities) + len(stored_a) + len(stored_d) > limit:
        raise Conflict("Affected closure exceeds bounded replay budget")
    return list(stored_a.values()), list(stored_d.values()), identities


class MergeStage:
    def __init__(self, store: Store, *, closure_limit: int = 10000):
        if not 1 <= closure_limit <= 10000:
            raise ValueError("Closure limit must be 1..10000")
        self.store = store
        self.closure_limit = closure_limit

    def apply(self, **command) -> dict:
        """Persist identity assessment, then automatically apply eligible work.

        A crash between the transactions leaves a resumable assessment. Preview
        and ordinary field-only updates do not create an assessment queue.
        """
        if command.get("preview") or not any(
            d["operation"] in {"bind", "merge"}
            for d in (command.get("decisions") or [])
        ):
            return self._execute(**command)
        for attempt in range(3):
            prepared = self.assess(**command)
            if not prepared.get("assessment_id"):
                # Duplicate delivery or decisions retained in an earlier batch.
                return self._execute(**command)
            try:
                return self.apply_assessment(
                    prepared["assessment_id"], run_id=command["run_id"]
                )
            except assessment.StaleAssessment:
                if attempt == 2:
                    raise
        raise AssertionError("Unreachable assessment retry state")

    def assess(self, **command) -> dict:
        """Retain a proposed binding/consolidation without committing masters.

        Invalid proposals retain their veto before the validation error is
        raised. Automatic scoring and qualification remain separate contracts.
        """
        if not any(
            d["operation"] in {"bind", "merge"}
            for d in (command.get("decisions") or [])
        ):
            raise ValueError("Assessment requires an identity proposal")
        run_id = command["run_id"]
        proposal = {k: v for k, v in command.items() if k not in {"run_id", "preview"}}
        for key, order in (
            ("assertions", "assertion_id"),
            ("identities", "entity_id"),
            ("deferred", "deferred_id"),
        ):
            if proposal.get(key):
                proposal[key] = sorted(proposal[key], key=lambda item: item[order])
        proposal["decisions"] = sorted(
            proposal["decisions"], key=lambda d: (d["at"], d["decision_id"])
        )
        context = {}
        try:
            result = self._execute(**{**command, "preview": True}, _context=context)
        except (Conflict, DBAPIError) as exc:
            # SQL driver exceptions can contain source values/connection details;
            # retain the SQLSTATE, never its full rendered query/parameters.
            veto = (
                str(exc)
                if isinstance(exc, Conflict)
                else f"database_validation:{getattr(exc.orig, 'pgcode', None)}"
            )
            assessment.record(
                self.store,
                {
                    "version": 1,
                    "command": proposal,
                    "outcome": "rejected",
                    "rule_version": "merge-validation-v1",
                    "vetoes": [veto],
                    **context,
                },
                run_id,
            )
            raise
        body = result.get("assessment")
        if body is None:
            return result
        return assessment.record(self.store, {**body, "command": proposal}, run_id)

    def apply_assessment(self, assessment_id: str, *, run_id: str) -> dict:
        with self.store.engine.connect() as conn:
            body = assessment.load(conn, assessment_id)
        try:
            return self._execute(
                **body["command"], run_id=run_id, assessment_id=assessment_id
            )
        except assessment.StaleAssessment:
            assessment.supersede(self.store, assessment_id, run_id)
            raise

    def _execute(
        self,
        *,
        batch_id: str,
        run_id: str,
        policy_digest: str,
        consumer: str,
        expected_checkpoint: int,
        checkpoint: int,
        as_of: str,
        assertions: list[dict] | None = None,
        decisions: list[dict] | None = None,
        identities: list[dict] | None = None,
        preview: bool = False,
        deferred: list[dict] | None = None,
        assessment_id: str | None = None,
        _context: dict | None = None,
    ) -> dict:
        assertions = sorted(assertions or [], key=lambda a: a["assertion_id"])
        decisions = sorted(decisions or [], key=lambda d: (d["at"], d["decision_id"]))
        identities = sorted(identities or [], key=lambda i: i["entity_id"])
        deferred = sorted(deferred or [], key=lambda d: d["deferred_id"])
        instant(as_of)
        if (
            len(assertions) + len(deferred) > 1000
            or len(decisions) > 1000
            or len(identities) > 1000
        ):
            raise ValueError("Unbounded batch")
        for a in assertions:
            validate_assertion(a)
        for record in deferred:
            validate_deferred(record)
        for d in decisions:
            if (
                digest({k: v for k, v in d.items() if k != "decision_id"})
                != d["decision_id"]
            ):
                raise Conflict("Decision hash mismatch")
        command = {
            "batch_id": batch_id,
            "policy_digest": policy_digest,
            "consumer": consumer,
            "expected_checkpoint": expected_checkpoint,
            "checkpoint": checkpoint,
            "as_of": as_of,
            "assertions": assertions,
            "decisions": decisions,
            "identities": identities,
        }
        # Preserve hashes of commands committed before deferred support existed.
        if deferred:
            command["deferred"] = deferred
        input_hash = digest(command)
        with self.store.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(730234)"))
            previous = conn.scalar(
                text("SELECT effects FROM mdm_v2.batch WHERE batch_id=:id"),
                {"id": batch_id},
            )
            if previous is not None:
                if previous.get("input_hash") != input_hash:
                    raise Conflict("Batch key reused with different command")
                if preview:
                    return {"preview": True, "duplicate": True, "effects": previous}
                return self.store.commit(conn, previous, run_id)
            if assessment_id is not None:
                assessment.check(conn, assessment_id)
            policy = conn.scalar(
                text("SELECT body FROM mdm_v2.policy WHERE digest=:digest"),
                {"digest": policy_digest},
            )
            if policy is None or policy.get("automatic_rules"):
                raise Conflict("Unknown or unqualified policy")
            stored_a, stored_d, stored_ids = load_closure(
                conn, assertions, decisions, limit=self.closure_limit
            )
            context = _context if _context is not None else {}
            if preview and any(d["operation"] in {"bind", "merge"} for d in decisions):
                all_assertions = [*stored_a, *assertions]
                keys = {a["subject"] for a in all_assertions}
                keys.update(i["entity_id"] for i in [*stored_ids, *identities])
                keys.update(k for d in [*stored_d, *decisions] for k in anchors(d))
                keys.update(
                    r["target_subject"]
                    for a in all_assertions
                    for r in a["relationships"]
                    if r.get("target_subject")
                )
                scope = {
                    "keys": sorted(keys),
                    "consumer": consumer,
                    "sources": sorted({a["source_code"] for a in all_assertions}),
                }
                context.update(
                    {
                        "scope": scope,
                        "snapshot": assessment.snapshot(conn, scope),
                        "retained": {
                            "assertion_ids": sorted(
                                a["assertion_id"] for a in stored_a
                            ),
                            "decision_ids": sorted(d["decision_id"] for d in stored_d),
                            "identities": sorted(
                                stored_ids, key=lambda i: i["entity_id"]
                            ),
                        },
                    }
                )
            evidence = {a["assertion_id"]: a for a in stored_a}
            for a in assertions:
                if a["assertion_id"] in evidence and a != evidence[a["assertion_id"]]:
                    raise Conflict("Evidence collision")
                evidence[a["assertion_id"]] = a
            all_d = {d["decision_id"]: d for d in stored_d}
            all_d.update({d["decision_id"]: d for d in decisions})
            all_ids = {i["entity_id"]: i for i in stored_ids}
            for i in identities:
                if i["entity_id"] in all_ids:
                    raise Conflict("Identity allocation already exists")
                UUID(i["entity_id"])
                instant(i["published_at"])
                all_ids[i["entity_id"]] = i
            for d in decisions:
                if d["operation"] == "bind" and not all(
                    k in evidence and evidence[k]["subject"] == d["subject"]
                    for k in d.get("evidence", [])
                ):
                    raise Conflict("Binding evidence does not describe its subject")
            state = replay(list(all_ids.values()), list(all_d.values()), as_of)
            if any(i["entity_id"] not in state.bindings.values() for i in identities):
                raise Conflict("New identities require an accepted source binding")
            claims = current_claims(
                list(evidence.values()), as_of, state.retired_sources
            )
            groups = defaultdict(list)
            for subject, entity in state.bindings.items():
                groups[state.canonical[entity]].append(subject)
            projected = {}
            reviews = []
            for entity_id, identity in sorted(all_ids.items()):
                root = state.canonical[entity_id]
                if root != entity_id:
                    projected[entity_id] = {
                        "entity_id": entity_id,
                        "kind": identity["kind"],
                        "canonical_id": root,
                        "status": "alias",
                    }
                    continue
                members = sorted(groups[entity_id])
                identifiers = defaultdict(set)
                conflicts = []
                for subject in members:
                    claim = claims.get(subject)
                    if not claim:
                        continue
                    if claim["kind"] != identity["kind"]:
                        conflicts.append(
                            {"reason": "kind_conflict", "subject": subject}
                        )
                    for namespace, value in claim["identifiers"].items():
                        identifiers[namespace].add(value)
                conflicts.extend(
                    {
                        "reason": "authoritative_identifier_conflict",
                        "namespace": ns,
                        "values": sorted(values),
                    }
                    for ns, values in identifiers.items()
                    if len(values) > 1
                )
                if conflicts and any(
                    d["operation"] in {"bind", "merge"} for d in decisions
                ):
                    raise Conflict(
                        "Identity decision has unresolved authoritative identifier or kind conflict"
                    )
                fields, profiles, field_reviews = select_fields(
                    identity["kind"],
                    members,
                    claims,
                    policy,
                    state.overrides,
                    as_of=as_of,
                    policy_digest=policy_digest,
                    entity_id=entity_id,
                )
                body = {
                    "entity_id": entity_id,
                    "kind": identity["kind"],
                    "canonical_id": entity_id,
                    "status": "review" if conflicts else "accepted",
                    "fields": fields,
                    "profiles": profiles,
                    "identifiers": {
                        k: sorted(v) for k, v in sorted(identifiers.items())
                    },
                    "subjects": members,
                }
                if conflicts:
                    # A prior projection depends on delivery order. Quarantine
                    # the current component deterministically; accepted history
                    # remains available through its retained generation.
                    body["fields"] = {}
                    body["profiles"] = []
                projected[entity_id] = body
                reviews.extend(
                    {**r, "entity_id": entity_id} for r in conflicts + field_reviews
                )
            for subject, claim in claims.items():
                if subject not in state.bindings:
                    reviews.append(
                        {
                            "reason": "binding_required",
                            "subject": subject,
                            "assertion_id": claim["assertion_id"],
                        }
                    )
            # Entity-scoped corrections cannot silently choose a partition after
            # reversal. Until explicitly attributed they remain review evidence.
            for override in state.overrides:
                if not override.get("subject"):
                    reviews.append(
                        {
                            "reason": "ambiguous_override_owner",
                            "decision_id": override["decision_id"],
                        }
                    )
            edges, edge_reviews = relationships.project(claims, state, projected, as_of)
            reviews.extend(edge_reviews)
            projections = [
                {"object_type": "entity", "object_id": key, "body": body}
                for key, body in projected.items()
            ]
            projections.extend(
                {
                    "object_type": "relationship",
                    "object_id": e["relationship_id"],
                    "body": e,
                }
                for e in edges
            )
            projections.extend(
                {
                    "object_type": "review",
                    "object_id": digest(r),
                    "body": {
                        **r,
                        "open": True,
                        "blocking": r["reason"] != "override_source_disagreement",
                        "affected_subjects": sorted(
                            {a["subject"] for a in evidence.values()}
                        ),
                        "affected_entities": sorted(all_ids),
                    },
                }
                for r in reviews
            )
            projections.extend(
                {
                    "object_type": "review",
                    "object_id": r["deferred_id"],
                    "body": {
                        "reason": r["reason"],
                        "deferred_id": r["deferred_id"],
                        "source_code": r["source_code"],
                        "publication_key": r["publication_key"],
                        "record_locator": r["record_locator"],
                        "open": True,
                        "blocking": True,
                    },
                }
                for r in deferred
            )
            # Retire old projected edges/reviews in the affected component only.
            old = rows(
                conn,
                """SELECT object_type,object_id,body FROM mdm_v2.projection WHERE
             (object_type='relationship' AND (body->>'source_id'=ANY(:ids) OR body->>'target_id'=ANY(:ids))) OR
             (object_type='review' AND (body->>'entity_id'=ANY(:ids) OR body->>'subject'=ANY(:subjects) OR body->'affected_subjects' ?| CAST(:subjects AS text[]))) LIMIT :lim""",
                ids=sorted(all_ids),
                subjects=sorted({a["subject"] for a in evidence.values()}),
                lim=self.closure_limit + 1,
            )
            if len(old) > self.closure_limit:
                raise Conflict("Projection retirement exceeds bounded budget")
            live = {(p["object_type"], p["object_id"]) for p in projections}
            for p in old:
                if (p["object_type"], p["object_id"]) not in live:
                    projections.append(
                        {**p, "body": {**p["body"], "retired": True, "open": False}}
                    )
            if len(projections) > self.closure_limit:
                raise Conflict("Projection exceeds bounded budget")
            generation = conn.scalar(
                text("SELECT coalesce(max(generation),0) FROM mdm_v2.batch")
            )
            request = {
                **command,
                "input_hash": input_hash,
                "expected_generation": generation,
                "decisions": [
                    d
                    for d in decisions
                    if d["decision_id"] not in {s["decision_id"] for s in stored_d}
                ],
                "projections": sorted(
                    projections, key=lambda p: (p["object_type"], p["object_id"])
                ),
                "source_accounting": {
                    "normalized": len(assertions),
                    "deferred": len(deferred),
                    "total": len(assertions) + len(deferred),
                },
            }
            if preview:
                # Exercise the identical SQL validation/permissions boundary,
                # through a capability that always rolls back its inner writes.
                conn.execute(
                    text("SELECT mdm_v2.preview_batch(:request,CAST(:run AS uuid))"),
                    {"request": canonical(request), "run": run_id},
                )
                candidate = None
                if any(
                    d["operation"] in {"bind", "merge"} for d in request["decisions"]
                ):
                    before = old + rows(
                        conn,
                        """SELECT object_type,object_id,body FROM mdm_v2.projection
                        WHERE object_type='entity' AND object_id=ANY(:ids) LIMIT :lim""",
                        ids=sorted(all_ids),
                        lim=self.closure_limit + 1,
                    )
                    if len(before) > self.closure_limit:
                        raise Conflict(
                            "Assessment projection history exceeds bounded budget"
                        )
                    candidate = {
                        "version": 1,
                        "command": command,
                        "outcome": "ready",
                        "rule_version": "merge-validation-v1",
                        "vetoes": [],
                        **context,
                        "before": sorted(
                            before, key=lambda p: (p["object_type"], p["object_id"])
                        ),
                        "effects": {
                            k: v
                            for k, v in request.items()
                            if k != "expected_generation"
                        },
                    }
                conn.rollback()
                return {
                    "preview": True,
                    "duplicate": False,
                    "effects": request,
                    "assessment": candidate,
                }
            if assessment_id is not None:
                request["assessment_id"] = assessment_id
            return self.store.commit(conn, request, run_id)

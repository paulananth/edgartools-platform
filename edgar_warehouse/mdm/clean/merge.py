"""One bounded, atomic Merge Stage for all Clean MDM writers.

The retained decision graph supplies identity; source policy supplies fields.
Identifier-only automatic binding runs through the same assessment (ticket
04); automatic consolidation and fuzzy binding are not enabled.
"""

from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import assessment, binding, matching, relationships
from .activation import check_policy
from .evidence import instant, validate_assertion, validate_deferred
from .identity import replay
from .store import Conflict, Store, canonical, digest, rows
from .survivorship import PROFILE_IDENTITY, current_claims, select_fields


def anchors(decision: dict) -> set[str]:
    return {
        str(decision[k])
        for k in ("subject", "entity_id", "left", "right", "target", "decision_id")
        if decision.get(k)
    }


def check_company_sources(policy: dict, assertions: list[dict]) -> None:
    """A kind-level fill rule must name every Company source now in scope.

    A policy may be registered before a later source dataset, but once that
    source first arrives, an incorrect priority name must fail the batch
    instead of silently omitting all its fields.
    """
    defaults = (policy.get("kinds") or {}).get("company", {}).get("defaults")
    if not defaults:
        return
    declared = set(defaults.get("sources", []))
    present = {a["source_code"] for a in assertions if a["kind"] == "company"}
    missing = present - declared
    if missing:
        raise Conflict(
            "Company policy has no source priority for: " + ", ".join(sorted(missing))
        )


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

        Active identifier rules may propose bindings and new Companies for the
        batch's records (ticket 04). Every proposal, the caller's or a rule's,
        is assessed before it commits (Q13); a load batch with nothing to bind
        keeps its direct path. A crash between the transactions leaves an
        assessment no one applies: the next run proposes again with fresh ids,
        and committing the batch closes the orphan (migration 040).
        """
        if command.get("preview"):
            return self._execute(**command, automatic=self.propose(**command))
        for attempt in range(3):
            # Re-proposed on every attempt: a stale assessment means master
            # state moved, and the next proposal must see where it moved to.
            automatic = self.propose(**command)
            if not _identity_work(command.get("decisions"), automatic):
                return self._execute(**command, automatic=automatic)
            prepared = self.assess(**command, automatic=automatic)
            if not prepared.get("assessment_id"):
                # Duplicate delivery or decisions retained in an earlier batch.
                return self._execute(**command, automatic=automatic)
            try:
                return self.apply_assessment(
                    prepared["assessment_id"], run_id=command["run_id"]
                )
            except assessment.StaleAssessment:
                if attempt == 2:
                    raise
        raise AssertionError("Unreachable assessment retry state")

    def propose(self, **command) -> dict:
        """What the policy's active identifier and name rules would bind or create."""
        with self.store.engine.connect() as conn:
            policy = conn.scalar(
                text("SELECT body FROM mdm_v2.policy WHERE digest=:digest"),
                {"digest": command["policy_digest"]},
            )
            if policy is None:
                return binding.nothing()
            proposed = binding.propose(
                conn,
                policy,
                assertions=command.get("assertions") or [],
                decisions=command.get("decisions") or [],
                identities=command.get("identities") or [],
                as_of=command["as_of"],
            )
            # Identifier proposals first: a record they bind is not name-matched,
            # and an SEC record they bind in this batch holds its Company for
            # the name rules (ticket 08).
            named = matching.propose(
                conn,
                policy,
                assertions=command.get("assertions") or [],
                decisions=(command.get("decisions") or []) + proposed["decisions"],
                as_of=command["as_of"],
            )
            for part in ("decisions", "reviews"):
                proposed[part] += named[part]
            return proposed

    def assess(self, *, automatic: dict | None = None, **command) -> dict:
        """Retain a proposed binding/consolidation without committing masters.

        Invalid proposals retain their veto before the validation error is
        raised. A rule's proposals are kept beside the caller's command, never
        inside it, so the command's hash stays the caller's own.
        """
        if not _identity_work(command.get("decisions"), automatic):
            raise ValueError("Assessment requires an identity proposal")
        run_id = command["run_id"]
        proposal = {k: v for k, v in command.items() if k not in {"run_id", "preview"}}
        for key, order in (
            ("assertions", "assertion_id"),
            ("identities", "entity_id"),
            ("deferred", "deferred_id"),
            ("occurrences", "assertion_id"),
        ):
            if proposal.get(key):
                proposal[key] = sorted(proposal[key], key=lambda item: item[order])
        if proposal.get("decisions"):
            # A load batch whose only identity work is a rule's has none.
            proposal["decisions"] = sorted(
                proposal["decisions"], key=lambda d: (d["at"], d["decision_id"])
            )
        context = {}
        try:
            result = self._execute(
                **{**command, "preview": True}, automatic=automatic, _context=context
            )
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
                    **(
                        {"automatic": automatic}
                        if _identity_work([], automatic)
                        else {}
                    ),
                    **context,
                },
                run_id,
            )
            raise
        body = result.get("assessment")
        if body is None:
            return result
        kept = {"automatic": automatic} if _identity_work([], automatic) else {}
        return assessment.record(
            self.store, {**body, "command": proposal, **kept}, run_id
        )

    def apply_assessment(self, assessment_id: str, *, run_id: str) -> dict:
        with self.store.engine.connect() as conn:
            body = assessment.load(conn, assessment_id)
        try:
            return self._execute(
                **body["command"],
                run_id=run_id,
                assessment_id=assessment_id,
                automatic=body.get("automatic"),
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
        occurrences: list[dict] | None = None,
        source_family: str | None = None,
        publication_family: str | None = None,
        committed_publication: str | None = None,
        continuity_proof: dict | None = None,
        assessment_id: str | None = None,
        automatic: dict | None = None,
        _context: dict | None = None,
    ) -> dict:
        assertions = sorted(assertions or [], key=lambda a: a["assertion_id"])
        decisions = sorted(decisions or [], key=lambda d: (d["at"], d["decision_id"]))
        identities = sorted(identities or [], key=lambda i: i["entity_id"])
        deferred = sorted(deferred or [], key=lambda d: d["deferred_id"])
        occurrences = _occurrences(occurrences or [], assertions)
        instant(as_of)
        if (
            len(assertions) + len(deferred) > 1000
            or len(decisions) > 1000
            or len(identities) > 1000
        ):
            raise ValueError("Unbounded batch")
        for a in assertions:
            validate_assertion(a)
            # The Stage hashes a profile's identifying values as text (038).
            if any(
                not isinstance(p.get(k), (str, type(None)))
                for p in a["profiles"]
                for k in PROFILE_IDENTITY
            ):
                raise Conflict("Profile identifying values must be text")
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
        # And before bronze occurrences existed (ticket 10).
        if occurrences:
            command["occurrences"] = occurrences
        family_metadata = {
            "source_family": source_family,
            "publication_family": publication_family,
            "committed_publication": committed_publication,
            "continuity_proof": continuity_proof,
        }
        if any(value is not None for value in family_metadata.values()):
            if (
                not all(
                    isinstance(value, str) and value.strip()
                    for value in (
                        source_family,
                        publication_family,
                        committed_publication,
                    )
                )
                or not isinstance(continuity_proof, dict)
                or not continuity_proof
            ):
                raise ValueError(
                    "Family checkpoint requires both families, publication identity and continuity proof"
                )
            command.update(family_metadata)
        input_hash = digest(command)
        # A rule's proposals join the working sets only after the caller's
        # command is hashed: they carry fresh ids, so hashing them would make
        # a redelivered batch look like a different command (ticket 04).
        automatic = automatic or binding.nothing()
        for d in automatic["decisions"]:
            if (
                digest({k: v for k, v in d.items() if k != "decision_id"})
                != d["decision_id"]
            ):
                raise Conflict("Decision hash mismatch")
        decisions = sorted(
            [*decisions, *automatic["decisions"]],
            key=lambda d: (d["at"], d["decision_id"]),
        )
        identities = sorted(
            [*identities, *automatic["identities"]], key=lambda i: i["entity_id"]
        )
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
            if policy is None:
                raise Conflict("Unknown or unqualified policy")
            # Again per batch, not only at registration: a body that reached
            # the store another way, or a build that no longer holds a named
            # primitive, is refused here the same way (`policy-language.md` §10).
            check_policy(policy)
            # Under the lock, every rule proposal is re-checked: a concurrent
            # run may have bound its identifier, given it to another Company,
            # or put the target Company in review since it was assessed.
            # Re-assess rather than mint twice or join the wrong Company.
            if not preview and binding.proposal_is_stale(conn, policy, automatic):
                raise assessment.StaleAssessment(
                    "A rule's proposal no longer holds; re-assess"
                )
            # A rule's new Company is published no earlier than the newest
            # identity already stored, so a backdated batch cannot create the
            # Company that survives every later merge (ticket 04; also
            # refused in SQL, 040).
            if automatic["identities"] and conn.scalar(
                text(
                    """SELECT EXISTS(SELECT 1 FROM mdm_v2.identity
                    WHERE published_at > CAST(:t AS timestamptz))"""
                ),
                {"t": min(i["published_at"] for i in automatic["identities"])},
            ):
                raise Conflict(
                    "A new Company would be published before an identity already stored"
                )
            stored_a, stored_d, stored_ids = load_closure(
                conn, assertions, decisions, limit=self.closure_limit
            )
            check_company_sources(policy, [*stored_a, *assertions])
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
                if source_family is not None:
                    scope.update(
                        source_family=source_family,
                        publication_family=publication_family,
                    )
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
            reviews.extend(automatic["reviews"])
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
            deferred_contracts = {
                row["source_code"]: row["body"]
                for row in rows(
                    conn,
                    "SELECT source_code,body FROM mdm_v2.dataset WHERE source_code=ANY(:codes)",
                    codes=sorted({r["source_code"] for r in deferred}),
                )
            }
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
                        "blocking": r["reason"]
                        not in deferred_contracts.get(r["source_code"], {}).get(
                            "nonblocking_deferred_reasons", []
                        ),
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
                "identities": identities,
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


def _occurrences(occurrences: list[dict], assertions: list[dict]) -> list[dict]:
    """The bronze object each reading of this batch was delivered in.

    Delivery details are not part of a source assertion, so a batch names them
    beside its readings; the Stage keeps the winning reading's (ticket 10).
    """
    ids = {a["assertion_id"] for a in assertions}
    seen = set()
    for o in occurrences:
        if (
            not isinstance(o, dict)
            or set(o) != {"assertion_id", "object", "sha256", "locator"}
            or not isinstance(o["assertion_id"], str)
            or o["assertion_id"] not in ids
            or o["assertion_id"] in seen
            or not all(isinstance(o[k], str) and o[k] for k in ("object", "locator"))
            or not isinstance(o["sha256"], str)
            or not re.fullmatch("[0-9a-f]{64}", o["sha256"])
        ):
            raise Conflict("Invalid bronze occurrence")
        seen.add(o["assertion_id"])
    return sorted(occurrences, key=lambda o: o["assertion_id"])


def _identity_work(decisions: list[dict] | None, automatic: dict | None) -> bool:
    """Whether a batch proposes any binding or consolidation to assess."""
    return any(d["operation"] in {"bind", "merge"} for d in decisions or []) or bool(
        (automatic or {}).get("decisions")
    )

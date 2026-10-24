"""One atomic Merge Stage for all MDM writers.

Record by record (ticket 77): each record of a batch finds its master by an
identifier rule, or a new one is made; only the masters a batch touches are
replayed, from their retained decisions and their source records, with the
links they start or that point into a master whose identity changed (`scope`).
Source policy supplies fields. Automatic consolidation and fuzzy binding are
not enabled.
"""

from __future__ import annotations

import re
from collections import defaultdict
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import assessment, binding, correction, limits, matching, relationships
from . import scope as scoping
from .activation import check_policy
from .evidence import PROFILE_KINDS, instant, validate_assertion, validate_deferred
from .identity import replay
from .store import Conflict, Store, canonical, digest, rows, storage_adapter
from .survivorship import PROFILE_IDENTITY, current_claims


def _disposition(reason: str) -> dict:
    """How a review stands: open for a steward, or a link waiting for its
    other end to become an accepted entity. A waiting link is no steward's
    review, never blocks, and is re-checked when that end is saved (mastering
    to-do 13; operator, 2026-10-02: "Wait quietly")."""
    if reason in relationships.WAITING:
        return {"open": False, "blocking": False, "waiting_for_end": True}
    return {"open": True, "blocking": reason != "override_source_disagreement"}


def review_scope(
    review: dict,
    members: dict,
    canonical: dict,
    evidence: dict,
    decisions: dict,
    within: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """The records and Companies a review is about: its record, its Company's
    records, the Companies a link review names, and for an override with no
    record, its Company and its evidence (platform validation 05b).

    `members` maps each current Company to its records. A later save that
    touches any of its records reads all of them (`scope`) and finds the
    review by these alone. A review that names no record falls back to every
    record of the masters the batch touches (`within`), rather than block
    their later saves.
    """
    entities = set(review.get("entities", []))
    subjects = set()
    if review.get("entity_id"):
        entities.add(review["entity_id"])
    if review.get("subject"):
        subjects.add(review["subject"])
    override = (
        decisions.get(review["decision_id"], {})
        if review["reason"] == "ambiguous_override_owner"
        else {}
    )
    if override.get("entity_id"):
        entities.add(override["entity_id"])
    subjects.update(
        evidence[k]["subject"] for k in override.get("evidence", []) if k in evidence
    )
    entities = {canonical.get(e, e) for e in entities}
    for entity in entities:
        subjects.update(members.get(entity, []))
    if not subjects:
        subjects = {
            a["subject"] for a in evidence.values() if within is None or a["subject"] in within
        }
    return sorted(subjects), sorted(entities)


def check_source_priorities(policy: dict, assertions: list[dict]) -> None:
    """A kind-level fill rule must name every source of that kind in scope.

    A policy may be registered before a later source dataset, but once that
    source first arrives, an incorrect priority name must fail the batch
    instead of silently omitting all its fields.
    """
    present = defaultdict(set)
    for assertion in assertions:
        present[assertion["kind"]].add(assertion["source_code"])
    for kind, block in sorted((policy.get("kinds") or {}).items()):
        defaults = block.get("defaults")
        if not defaults:
            continue
        missing = present[kind] - set(defaults.get("sources", []))
        if missing:
            raise Conflict(
                f"{kind} policy has no source priority for: " + ", ".join(sorted(missing))
            )


def link_only(claim: dict) -> bool:
    """A reading that only states links between other records (a GLEIF
    relationship record): it has no identity of its own to bind."""
    return (
        bool(claim["relationships"])
        and not claim["fields"]
        and not claim["identifiers"]
        and all(r.get("source_subject") for r in claim["relationships"])
    )


class MergeStage:
    def __init__(self, store: Store):
        self.store = store

    def apply(self, **command) -> dict:
        """Match the batch's records, then save it, in one transaction.

        Active identifier and name rules may propose bindings and new masters
        for the batch's records (ticket 04). Every proposal, the caller's or a
        rule's, is recorded before the batch's writes, in the same transaction
        (Q13; operator, 2026-10-14: "Same transaction"); a refused one is kept in
        a transaction of its own. A rule's proposal another run has overtaken is
        proposed again.
        """
        if getattr(self.store,"read_only",False):
            raise Conflict("A read-only MDM store cannot admit a merge")
        if command.get("preview"):
            return self._execute(**command, automatic=self.propose(**command))
        for attempt in range(3):
            automatic = self.propose(**command)
            if not _identity_work(command.get("decisions"), automatic):
                return self._execute(**command, automatic=automatic)
            proposal, kept = _proposal(command), _kept(automatic)
            try:
                return self._execute(**command, automatic=automatic, _record={"command": proposal, **kept})
            except assessment.StaleAssessment:
                if attempt == 2:
                    raise
            except (Conflict, DBAPIError) as exc:
                self._reject(proposal, kept, exc, command["run_id"])
                raise
        raise AssertionError("Unreachable assessment retry state")

    def propose(self, **command) -> dict:
        """What the policy's active identifier and name rules would bind or create."""
        return self.propose_on(self.store.engine, **command)

    @staticmethod
    def propose_on(engine, **command) -> dict:
        """The normal read phase, independently callable before admitting writes."""
        from .record_reads import for_connection, RecordReader
        with engine.connect() as connection:
            conn=for_connection(connection)
            generation=conn.adapter.generation(connection=connection) if isinstance(conn,RecordReader) else None
            policy = storage_adapter().registered_policy(connection, command["policy_digest"])
            if policy is None:
                return binding.nothing()
            # A record this batch releases (a revoked bind, ticket 13) or
            # lifts from quarantine is reconsidered by the rules from its
            # current Stage reading; a quarantined record is left out of
            # matching. Each is looked up once per batch.
            decisions = command.get("decisions") or []
            released = correction.released(conn, decisions)
            incoming = (command.get("assertions") or []) + correction.readings(
                conn, released | correction.lifted(conn, decisions)
            )
            quarantined = correction.quarantined(
                conn, {a["subject"] for a in incoming}, decisions
            )
            candidates = [a for a in incoming if a["subject"] not in quarantined]
            proposed = binding.propose(
                conn,
                policy,
                assertions=candidates,
                decisions=decisions,
                identities=command.get("identities") or [],
                as_of=command["as_of"],
                released=released,
            )
            # Identifier proposals first: a record they bind is not name-matched,
            # and an SEC record they bind in this batch holds its Company for
            # the name rules (ticket 08).
            named = matching.propose(
                conn,
                policy,
                assertions=candidates,
                decisions=decisions + proposed["decisions"],
                as_of=command["as_of"],
                released=released,
            )
            for part in ("decisions", "reviews"):
                proposed[part] += named[part]
            if generation is not None:
                proposed["observed_generation"]=generation
            return proposed

    @staticmethod
    def read_scope_on(engine, assertions, decisions):
        """Read the same affected-identity scope used by the normal Merge Stage."""
        from .record_reads import for_connection
        with engine.connect() as connection:
            conn=for_connection(connection)
            scope=scoping.identities(conn,assertions,decisions)
            sources={body["source_code"] for body in [*scope.readings.values(),*assertions]}
            scope.decisions.update(scoping.retirements(conn,sources))
            scope.stored_decisions.update(scope.decisions)
            return scope

    def read_scope(self, assertions, decisions):
        return self.read_scope_on(self.store.engine,assertions,decisions)

    def assess(self, *, automatic: dict | None = None, **command) -> dict:
        """Record a proposal without saving its batch, for `apply_assessment`.

        A refused proposal is recorded before the error is raised. A rule's
        proposals are kept beside the caller's command, never inside it, so
        the command's hash stays the caller's own.
        """
        if getattr(self.store,"read_only",False):
            raise Conflict("A read-only MDM store cannot retain an assessment")
        if not _identity_work(command.get("decisions"), automatic):
            raise ValueError("Assessment requires an identity proposal")
        proposal, kept = _proposal(command), _kept(automatic)
        try:
            result = self._execute(**{**command, "preview": True}, automatic=automatic)
        except (Conflict, DBAPIError) as exc:
            self._reject(proposal, kept, exc, command["run_id"])
            raise
        body = result.get("assessment")
        if body is None:
            return result
        return assessment.record(
            self.store, {**body, "command": proposal, **kept}, command["run_id"]
        )

    @staticmethod
    def _check_rule_proposals(conn, policy_digest: str, automatic: dict | None, decisions: list[dict]) -> dict:
        """Under the lock, every rule proposal is re-checked: a concurrent run may
        have bound its identifier, given it to another Company, or published a
        newer Company of its kind since it was proposed. Propose again rather
        than mint twice, join the wrong Company, or publish a new Company before
        one already stored. A preview passes no proposals and checks only the
        policy. Returns the policy."""
        policy = storage_adapter().registered_policy(conn, policy_digest)
        if policy is None:
            raise Conflict("Unknown or unqualified policy")
        # Again per batch, not only at registration: a body that reached
        # the store another way, or a build that no longer holds a named
        # primitive, is refused here the same way (`policy-language.md` §10).
        check_policy(policy)
        if automatic is not None and binding.proposal_is_stale(
            conn, policy, automatic, correction.released(conn, decisions)
        ):
            raise assessment.StaleAssessment("A rule's proposal no longer holds; re-assess")
        return policy

    def _reject(self, proposal: dict, kept: dict, exc: Exception, run_id: str) -> None:
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
                **kept,
            },
            run_id,
        )

    def apply_assessment(self, assessment_id: str, *, run_id: str) -> dict:
        """Save the batch a recorded proposal computed. It is computed again
        under the lock; if the save finds it writes other than the proposal's
        effects, or the proposal already applied, it is stale and superseded."""
        if getattr(self.store,"read_only",False):
            raise Conflict("A read-only MDM store cannot apply an assessment")
        with self.store.engine.connect() as conn:
            body = assessment.load(conn, assessment_id)
        if body["outcome"] != "ready":
            raise Conflict("Rejected identity assessment cannot be applied")
        try:
            return self._execute(
                **body["command"],
                run_id=run_id,
                assessment_id=assessment_id,
                automatic=body.get("automatic"),
            )
        except DBAPIError as exc:
            if not assessment.stale(exc):
                raise
            assessment.supersede(self.store, assessment_id, run_id)
            raise assessment.StaleAssessment("Stale identity assessment; recompute proposal") from None
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
        _record: dict | None = None,
    ) -> dict:
        if getattr(self.store,"read_only",False):
            raise Conflict("A read-only MDM store cannot admit a merge")
        assertions = sorted(assertions or [], key=lambda a: a["assertion_id"])
        decisions = sorted(decisions or [], key=lambda d: (d["at"], d["decision_id"]))
        identities = sorted(identities or [], key=lambda i: i["entity_id"])
        deferred = sorted(deferred or [], key=lambda d: d["deferred_id"])
        occurrences = _occurrences(occurrences or [], assertions)
        instant(as_of)
        if (
            len(assertions) + len(deferred) > limits.BATCH_RECORDS
            or len(decisions) > limits.BATCH_RECORDS
            or len(identities) > limits.BATCH_RECORDS
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
        _check_hashes(decisions)
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
        _check_hashes(automatic["decisions"])
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
                text("SELECT effects FROM mdm.batch WHERE batch_id=:id"),
                {"id": batch_id},
            )
            if previous is not None:
                if previous.get("input_hash") != input_hash:
                    raise Conflict("Batch key reused with different command")
                if preview:
                    return {"preview": True, "duplicate": True, "effects": previous}
                return self.store.commit(conn, previous, run_id)
            policy = self._check_rule_proposals(
                conn, policy_digest, None if preview else automatic, decisions
            )
            types = relationships.types_of(policy)
            # The masters this batch touches, whole; nothing it is only
            # linked to (ticket 77, `scope`).
            scope = scoping.identities(conn, assertions, decisions)
            check_source_priorities(policy, [*scope.readings.values(), *assertions])
            evidence = dict(scope.readings)
            for a in assertions:
                if a["assertion_id"] in evidence and a != evidence[a["assertion_id"]]:
                    raise Conflict("Evidence collision")
                evidence[a["assertion_id"]] = a
            all_d = {**scope.decisions, **scoping.retirements(conn)}
            all_d.update({d["decision_id"]: d for d in decisions})
            scope.decisions.update({d["decision_id"]: d for d in decisions})
            all_ids = {i["entity_id"]: i for i in scope.identities}
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
            correction.check_lifts(all_d, decisions, policy_digest)
            state = replay(list(all_ids.values()), list(all_d.values()), as_of)
            if any(i["entity_id"] not in state.bindings.values() for i in identities):
                raise Conflict("New identities require an accepted source binding")
            claims = current_claims(
                list(evidence.values()), as_of, state.retired_sources
            )
            from edgar_warehouse.rules.source_engine import prepare_master_records, resolve_record_bindings

            try:
                projected, reviews, groups = prepare_master_records({
                    "identities": all_ids, "canonical": state.canonical,
                    "bindings": state.bindings, "quarantined": state.quarantined,
                    "claims": claims, "policy": policy, "overrides": state.overrides,
                    "decisions": decisions, "as_of": as_of, "policy_digest": policy_digest,
                    "profile_kinds": {role: sorted(kinds) for role, kinds in PROFILE_KINDS.items()},
                })
            except ValueError as error:
                raise Conflict(str(error)) from None
            reviews.extend(automatic["reviews"])
            # The links: those the affected masters start, and those into a
            # master whose identity changed; a far end is read as stored.
            stored = scoping.stored_masters(conn, projected)
            changed = {e for e, b in projected.items() if scoping.identity_changed(b, stored.get(e))}
            # Its survivor now and before: a link into either may move.
            changed |= {state.canonical[e] for e in changed} | {
                stored[e].get("canonical_id") or e for e in changed if e in stored
            }
            scope.masters = set(projected)
            scope.replayed = resolve_record_bindings({
                "subjects": sorted(scope.subjects), "bindings": state.bindings,
                "canonical": state.canonical,
            })
            # Every affected master starts its links here, a merged-away one
            # too: its stored links are read, and retired once it is an alias.
            scoping.links(conn, scope, set(projected), changed, types, assertions)
            linked = {**scope.readings, **evidence}
            ends = SimpleNamespace(
                bindings={**scope.bound, **state.bindings},
                canonical={**{e: scope.root(e) for e in scope.stored}, **state.canonical},
            )
            old = {
                (p["object_type"], p["object_id"]): p["body"]
                for p in scoping.stored_links_and_reviews(conn, scope)
            }
            edges, edge_reviews = relationships.project(
                current_claims(list(linked.values()), as_of, state.retired_sources),
                ends,
                {**{scope.root(e): scope.stored[scope.root(e)] for e in scope.stored}, **projected},
                as_of,
                types=types,
                stored={key: body for (kind, key), body in old.items() if kind == "relationship"},
            )
            edges = [e for e in edges if scope.owns_link(e)]
            reviews.extend(edge_reviews)
            scope.links = {e["relationship_id"] for e in edges} | {
                k for t, k in old if t == "relationship"
            }
            # Only what changed is written: a master, link or review equal to
            # its stored body is left as it is.
            projections = [
                {"object_type": "entity", "object_id": key, "body": body}
                for key, body in projected.items()
                if body != stored.get(key)
            ]
            projections.extend(
                {"object_type": "relationship", "object_id": e["relationship_id"], "body": e}
                for e in edges
                if e != old.get(("relationship", e["relationship_id"]))
            )
            live = {("relationship", e["relationship_id"]) for e in edges}
            for r in reviews:
                subjects, entities = review_scope(
                    r, groups, state.canonical, evidence, all_d, within=scope.subjects
                )
                body = {
                    **r,
                    **_disposition(r["reason"]),
                    "affected_subjects": subjects,
                    "affected_entities": entities,
                }
                if r not in automatic["reviews"] and not scope.owns(body):
                    continue
                key = ("review", digest(r))
                live.add(key)
                if body != old.get(key):
                    projections.append({"object_type": "review", "object_id": key[1], "body": body})
            deferred_contracts = storage_adapter().dataset_contracts(
                conn, (r["source_code"] for r in deferred)
            )
            # A set-aside record's review is always sent: the save checks it.
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
            # Retire the batch's own links and reviews it no longer produces.
            for (kind, key), body in sorted(old.items()):
                if (kind, key) in live or body.get("retired"):
                    continue
                if kind == "review" and not scope.owns(body):
                    continue
                projections.append(
                    {"object_type": kind, "object_id": key,
                     "body": {**body, "retired": True, "open": False, "waiting_for_end": False}}
                )
            generation = conn.scalar(
                text("SELECT coalesce(max(generation),0) FROM mdm.batch")
            )
            request = {
                **command,
                "identities": identities,
                "input_hash": input_hash,
                "expected_generation": generation,
                "decisions": [d for d in decisions if d["decision_id"] not in scope.stored_decisions],
                "projections": sorted(
                    projections, key=lambda p: (p["object_type"], p["object_id"])
                ),
                "source_accounting": {
                    "normalized": len(assertions),
                    "deferred": len(deferred),
                    "total": len(assertions) + len(deferred),
                },
            }
            effects = {k: v for k, v in request.items() if k != "expected_generation"}
            if preview:
                # Exercise the identical SQL validation/permissions boundary,
                # through a capability that always rolls back its inner writes.
                conn.execute(
                    text("SELECT mdm.preview_batch(:request,CAST(:run AS uuid))"),
                    {"request": canonical(request), "run": run_id},
                )
            candidate = None
            if (preview or _record is not None) and _identity_work(request["decisions"], None):
                before = [
                    {"object_type": t, "object_id": k, "body": b} for (t, k), b in old.items()
                ] + [
                    {"object_type": "entity", "object_id": k, "body": b} for k, b in stored.items()
                ]
                candidate = {
                    "version": 1,
                    "command": command,
                    "outcome": "ready",
                    "rule_version": "merge-validation-v1",
                    "vetoes": [],
                    "before": sorted(before, key=lambda p: (p["object_type"], p["object_id"])),
                    "effects": effects,
                }
            if preview:
                conn.rollback()
                return {
                    "preview": True,
                    "duplicate": False,
                    "effects": request,
                    "assessment": candidate,
                }
            if assessment_id is not None:
                # The save checks the batch equals the proposal's effects.
                request["assessment_id"] = assessment_id
            elif candidate is not None:
                # The proposal first, then the batch, in one commit (Q13).
                self.store._authorize(conn)
                request["assessment_id"] = assessment.record_in(conn, {**candidate, **_record}, run_id)
            return self.store.commit(conn, request, run_id)


def _check_hashes(decisions: list[dict]) -> None:
    """A decision's id is the hash of its body."""
    for d in decisions:
        if digest({k: v for k, v in d.items() if k != "decision_id"}) != d["decision_id"]:
            raise Conflict("Decision hash mismatch")


def _proposal(command: dict) -> dict:
    """The caller's command as a proposal keeps it: its lists in a fixed order."""
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
    return proposal


def _kept(automatic: dict | None) -> dict:
    """A rule's proposals are kept beside the caller's command, never inside it."""
    return {"automatic": automatic} if _identity_work([], automatic) else {}


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

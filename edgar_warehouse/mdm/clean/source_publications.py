"""Read-only publication verification over the existing acquisition ledger.

No master writes, new source tables, or consumer completion claims. The v1
manifest is an adapter contract, not a claim that native GLEIF XML is supported.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import text

from .store import Conflict, Store, canonical, digest

HASH = re.compile(r"[0-9a-f]{64}\Z")
MANIFEST_LIMIT = 1024 * 1024
MEMBER_LIMIT = 1024 * 1024 * 1024
MAX_MEMBERS = 128
VERSIONS = (
    "contract_version",
    "parser_version",
    "schema_version",
    "configuration_version",
)
HASHES = ("raw_evidence_hash", "canonical_source_hash", "domain_content_hash")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Conflict("Duplicate JSON field")
        result[key] = value
    return result


def _hash(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise Conflict("Expected a lowercase SHA256 digest")
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise Conflict("Expected a nonempty source identity")
    return value


def _sequence(value):
    if type(value) is not int or value < 0:
        raise Conflict("Expected a nonnegative source sequence")
    return value


@dataclass(frozen=True)
class VerifiedPublication:
    """Canonical immutable proof; callers receive copies of its JSON content."""

    evidence_json: str

    @property
    def evidence(self):
        return json.loads(self.evidence_json)

    @property
    def proof_digest(self):
        return hashlib.sha256(self.evidence_json.encode()).hexdigest()


class PublicationVerifier:
    def __init__(
        self,
        ledger_engine,
        open_artifact: Callable[[str], AbstractContextManager[BinaryIO]],
    ):
        self.ledger_engine = ledger_engine
        self.open_artifact = open_artifact

    def _revision(self, conn, revision_id):
        try:
            UUID(str(revision_id))
        except ValueError as exc:
            raise Conflict("Invalid source revision identity") from exc
        row = (
            conn.execute(
                text("""SELECT r.*, EXISTS (
                SELECT 1 FROM public.source_fetch_decision d
                JOIN public.source_fetch_transition t USING (decision_id)
                WHERE d.decision_id=r.decision_id
                  AND d.source_family=r.source_family
                  AND d.logical_source_key=r.logical_source_key
                  AND d.observation_position=r.observation_position
                  AND t.to_state='CAPTURED'
            ) AS captured
            FROM public.source_revision r WHERE r.revision_id=:id"""),
                {"id": str(revision_id)},
            )
            .mappings()
            .one_or_none()
        )
        # Derived interpretations need a separately specified lineage contract.
        # Do not mistake mere row existence for a verified fresh capture.
        if row is None or not row["captured"] or row["parent_revision_id"] is not None:
            raise Conflict("Missing or unverified fresh source revision")
        return dict(row)

    def _bytes(self, revision, limit, *, retain=False):
        sha = hashlib.sha256()
        length = 0
        content = bytearray()
        with self.open_artifact(revision["bronze_artifact_reference"]) as stream:
            while chunk := stream.read(min(1024 * 1024, limit - length + 1)):
                length += len(chunk)
                if length > limit:
                    raise Conflict("Publication artifact exceeds verification bound")
                sha.update(chunk)
                if retain:
                    content.extend(chunk)
        if sha.hexdigest() != _hash(revision["raw_evidence_hash"]):
            raise Conflict("Source artifact digest mismatch")
        return bytes(content), length

    def verify(self, store: Store, *, source_code: str, manifest_revision_id: str):
        """Verify exactly the inventory pinned by a registered dataset contract.

        Artifact references come only from immutable revisions. The caller's
        reader enforces its approved local root or S3 bucket. Every byte is
        checked; canonical/domain hashes are compared with the pinned ledger
        interpretation, never recomputed using an unversioned parser.
        """
        with store.engine.connect() as conn:
            dataset = conn.execute(
                text("SELECT body FROM mdm_v2.dataset WHERE source_code=:code"),
                {"code": source_code},
            ).scalar_one_or_none()
        if dataset is None:
            raise Conflict("Unregistered publication dataset")
        contract = dataset.get("publication_contract", {})
        if not isinstance(contract, dict):
            raise Conflict("Unsupported publication contract")
        if (
            type(contract.get("version")) is not int
            or contract.get("version") != 1
            or contract.get("format") != "clean-mdm-publication-v1"
            or contract.get("continuity") != "sequence-predecessor-sha256-v1"
            or contract.get("publication_family")
            not in dataset.get("publication_families", [])
        ):
            raise Conflict("Unsupported publication contract")
        kinds = contract.get("required_members")
        if (
            not isinstance(kinds, list)
            or not kinds
            or len(kinds) > MAX_MEMBERS
            or any(not isinstance(k, str) or not k.strip() for k in kinds)
            or len(kinds) != len(set(kinds))
        ):
            raise Conflict("Invalid required member inventory")
        versions = contract.get("revision_versions", {})
        if (
            not isinstance(versions, dict)
            or set(versions) != set(VERSIONS)
            or any(not isinstance(v, str) or not v for v in versions.values())
        ):
            raise Conflict("Publication interpretation versions must be pinned")
        with self.ledger_engine.begin() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL ROLE edgartools_acquisition_processor"))
            manifest_revision = self._revision(conn, manifest_revision_id)
            raw, manifest_size = self._bytes(
                manifest_revision, MANIFEST_LIMIT, retain=True
            )
            try:
                manifest = json.loads(raw, object_pairs_hook=_object)
                # Reject NaN/Infinity, including nested unused metadata.
                canonical(manifest)
            except (ValueError, UnicodeError) as exc:
                raise Conflict("Invalid publication manifest JSON") from exc
            if (
                not isinstance(manifest, dict)
                or type(manifest.get("version")) is not int
                or manifest.get("version") != 1
            ):
                raise Conflict("Unsupported publication manifest version")
            family = _name(manifest.get("source_family"))
            publication_family = _name(manifest.get("publication_family"))
            publication = _name(manifest.get("publication"))
            if (
                family != dataset["family"]
                or publication_family != contract["publication_family"]
            ):
                raise Conflict("Publication family does not match registered dataset")
            sequence = _sequence(manifest.get("sequence"))
            mode = manifest.get("mode")
            coverage = manifest.get("coverage")
            scope = _name(manifest.get("replacement_scope"))
            if scope != contract.get("replacement_scope"):
                raise Conflict("Publication replacement scope mismatch")
            predecessor = manifest.get("predecessor")
            if mode == "full":
                if coverage != "COMPLETE" or predecessor is not None:
                    raise Conflict(
                        "A full baseline requires COMPLETE scope and no predecessor"
                    )
            elif mode == "delta":
                if coverage != "PARTIAL" or not isinstance(predecessor, dict):
                    raise Conflict(
                        "A delta requires PARTIAL scope and an explicit predecessor"
                    )
                if set(predecessor) != {"sequence", "manifest_sha256"}:
                    raise Conflict("Invalid predecessor metadata")
                if _sequence(predecessor["sequence"]) >= sequence:
                    raise Conflict("Publication sequence must advance")
                _hash(predecessor["manifest_sha256"])
            else:
                raise Conflict("Unsupported publication mode")

            def check_revision(revision):
                if (
                    revision["source_family"] != family
                    or revision["source_native_revision"] != publication
                    or revision["completeness_type"] != coverage
                    or revision["declared_replacement_scope"] != scope
                    or any(revision[k] != v for k, v in versions.items())
                ):
                    raise Conflict(
                        "Revision publication, coverage or interpretation mismatch"
                    )
                for key in HASHES:
                    _hash(revision[key])

            check_revision(manifest_revision)
            members = manifest.get("members")
            if not isinstance(members, list) or len(members) != len(kinds):
                raise Conflict("Publication member inventory is incomplete")
            captured_inventory = (
                conn.execute(
                    text("""SELECT revision_id, logical_source_key
                FROM public.source_revision
                WHERE source_family=:family AND source_native_revision=:publication
                LIMIT :bound"""),
                    {
                        "family": family,
                        "publication": publication,
                        "bound": MAX_MEMBERS + 2,
                    },
                )
                .mappings()
                .all()
            )
            captured_keys = [r["logical_source_key"] for r in captured_inventory]
            if len(captured_inventory) != len(members) + 1 or len(
                set(captured_keys)
            ) != len(captured_keys):
                raise Conflict("Missing, extra or conflicting publication revisions")
            captured_by_key = {
                r["logical_source_key"]: str(r["revision_id"])
                for r in captured_inventory
            }
            names, keys, ids = (
                set(),
                {manifest_revision["logical_source_key"]},
                {str(manifest_revision["revision_id"])},
            )
            inventory = []
            for member in members:
                if not isinstance(member, dict):
                    raise Conflict("Invalid publication member")
                name = _name(member.get("member"))
                key = _name(member.get("logical_source_key"))
                revision_id = captured_by_key.get(key)
                if revision_id is None:
                    raise Conflict("Missing member source revision")
                if (
                    name not in kinds
                    or name in names
                    or key in keys
                    or revision_id in ids
                ):
                    raise Conflict("Duplicate or unexpected member identity")
                names.add(name)
                keys.add(key)
                ids.add(revision_id)
                revision = self._revision(conn, revision_id)
                check_revision(revision)
                if revision["logical_source_key"] != key or any(
                    _hash(member.get(k)) != revision[k] for k in HASHES
                ):
                    raise Conflict("Member identity or interpretation digest mismatch")
                _, size = self._bytes(revision, MEMBER_LIMIT)
                if type(member.get("bytes")) is not int or member["bytes"] != size:
                    raise Conflict("Member byte count mismatch")
                inventory.append(
                    {
                        "member": name,
                        "logical_source_key": key,
                        "revision_id": revision_id,
                        "bytes": size,
                        **{k: revision[k] for k in HASHES},
                    }
                )
        inventory.sort(key=lambda member: member["member"])
        return VerifiedPublication(
            canonical(
                {
                    "version": 1,
                    "source_code": source_code,
                    "dataset_digest": digest(dataset),
                    "source_family": family,
                    "publication_family": publication_family,
                    "publication": publication,
                    "manifest_revision_id": str(manifest_revision["revision_id"]),
                    "manifest_sha256": manifest_revision["raw_evidence_hash"],
                    "sequence": sequence,
                    "mode": mode,
                    "coverage": coverage,
                    "replacement_scope": scope,
                    "predecessor": predecessor,
                    "members": inventory,
                    # Acquisition UUIDs are lineage, not source content identity.
                    "inventory_digest": digest(
                        [
                            {k: v for k, v in member.items() if k != "revision_id"}
                            for member in inventory
                        ]
                    ),
                    "verified_bytes": manifest_size
                    + sum(m["bytes"] for m in inventory),
                    "delivery_verified": True,
                }
            )
        )


def plan_continuity(
    publications: list[VerifiedPublication],
    *,
    target_sequence: int,
    previous: VerifiedPublication | None = None,
) -> dict:
    """Select the cheapest proven delta path; otherwise reconcile a full baseline.

    `previous` must represent a *fully consumed* verified publication loaded by
    the consumer, not a bounded batch cursor. This function only proposes work.
    It cannot advance a checkpoint or certify domain/downstream completion.
    """
    target_sequence = _sequence(target_sequence)
    if not publications or len(publications) > MAX_MEMBERS:
        raise Conflict("Supply 1..128 verified recovery candidates")
    docs = {p.proof_digest: p.evidence for p in publications}
    old = previous.evidence if previous else None
    scope_keys = (
        "source_code",
        "dataset_digest",
        "source_family",
        "publication_family",
        "replacement_scope",
    )
    scope = tuple(next(iter(docs.values()))[k] for k in scope_keys)
    if any(
        tuple(d[k] for k in scope_keys) != scope
        for d in [*docs.values(), *([old] if old else [])]
    ):
        raise Conflict("Recovery cannot mix datasets, scopes or sibling families")
    if old and old["sequence"] >= target_sequence:
        raise Conflict("Recovery target must advance the completed publication")
    identities = {old["publication"]: previous.proof_digest} if previous else {}
    for proof, doc in docs.items():
        native = doc["publication"]
        if native in identities and identities[native] != proof:
            raise Conflict("Conflicting evidence for one native publication")
        identities[native] = proof

    def path_from(start, *, baseline=None):
        # Increasing source sequences form a DAG; dynamic programming retains
        # the cheapest deterministic path to each (sequence, manifest hash).
        initial = (start["sequence"], start["manifest_sha256"])
        paths = {initial: ((0, 0, ()), [])}
        if baseline:
            paths[initial] = ((start["verified_bytes"], 1, (baseline,)), [baseline])
        for proof, doc in sorted(
            docs.items(), key=lambda item: (item[1]["sequence"], item[0])
        ):
            if doc["mode"] != "delta" or doc["sequence"] > target_sequence:
                continue
            pred = doc["predecessor"]
            parent = paths.get((pred["sequence"], pred["manifest_sha256"]))
            if parent is None:
                continue
            cost, route = parent
            next_cost = (
                cost[0] + doc["verified_bytes"],
                cost[1] + 1,
                (*cost[2], proof),
            )
            endpoint = (doc["sequence"], doc["manifest_sha256"])
            if endpoint not in paths or next_cost < paths[endpoint][0]:
                paths[endpoint] = (next_cost, [*route, proof])
        return [value for key, value in paths.items() if key[0] == target_sequence]

    paths = path_from(old) if old else []
    mode = "delta"
    if not paths:
        mode = "full_reconciliation"
        paths = [
            path
            for proof, doc in docs.items()
            if doc["mode"] == "full"
            and doc["sequence"] <= target_sequence
            and (old is None or doc["sequence"] > old["sequence"])
            for path in path_from(doc, baseline=proof)
        ]
    if not paths:
        raise Conflict(
            "Continuity gap: a verified full baseline is required for this family"
        )
    _, selected = min(paths)
    evidence = {
        "version": 1,
        **dict(zip(scope_keys, scope)),
        "recovery_mode": mode,
        "previous_proof_digest": previous.proof_digest if previous else None,
        "target_sequence": target_sequence,
        "publications": [{"proof_digest": p, "evidence": docs[p]} for p in selected],
        "consumption_complete": False,
        "downstream_complete": False,
    }
    return {**evidence, "proof_digest": digest(evidence)}

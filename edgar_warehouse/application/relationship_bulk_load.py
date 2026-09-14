"""CIK-batch resume helpers and insider-coverage checks.

silver-merge-engine-migration Ticket 11 deleted the Ticket 20 release workflow
(frozen candidate manifests, completion ledgers, gate attestations and release
evidence) this module was written for. What remains: batch identity and
remaining-batch helpers for the default Clean and Merge Filings resume
(``batch_silver_resume``), the accession path segment used by daily artifact
resume, and the insider-coverage inventory behind ``mdm verify-insider-coverage``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from edgar_warehouse.mdm.sql_fragments import prefer_non_owner_cik_qualify


class InventoryError(ValueError):
    pass


def batch_identity_for_ciks(ciks: Iterable[int | str]) -> str:
    """Stable 16-hex identity for one Strict Clean and Merge Filings CIK batch."""
    normalized = sorted(str(int(cik)) for cik in ciks)
    return hashlib.sha256(",".join(normalized).encode("utf-8")).hexdigest()[:16]


def batch_identity_from_done_marker_name(name: str) -> str | None:
    """Parse ``{batch_identity}.json`` child names under batch_done/."""
    raw = str(name or "").strip()
    if not raw.endswith(".json"):
        return None
    identity = raw[: -len(".json")].lower()
    if not re.fullmatch(r"[0-9a-f]{16}", identity):
        return None
    return identity


def list_done_batch_identities(child_names: Iterable[str]) -> set[str]:
    """Extract completed batch identities from batch_done directory child names."""
    done: set[str] = set()
    for name in child_names:
        identity = batch_identity_from_done_marker_name(name)
        if identity is not None:
            done.add(identity)
    return done


def _ciks_from_batch_row(batch: Mapping[str, object]) -> list[int]:
    cik_list = batch.get("cik_list")
    if isinstance(cik_list, str):
        parts = [part.strip() for part in cik_list.split(",") if part.strip()]
        if not parts:
            raise InventoryError("cik_batches row has empty cik_list")
        return [int(part) for part in parts]
    if isinstance(cik_list, list):
        if not cik_list:
            raise InventoryError("cik_batches row has empty cik_list")
        return [int(part) for part in cik_list]
    raise InventoryError("cik_batches row is missing cik_list")


def parse_cik_batches_jsonl(text: str) -> list[dict[str, object]]:
    """Parse Distributed Map CIK batch JSONL into row objects."""
    rows: list[dict[str, object]] = []
    for line_no, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InventoryError(f"invalid cik_batches JSONL on line {line_no}") from exc
        if not isinstance(payload, dict):
            raise InventoryError(f"cik_batches JSONL line {line_no} must be an object")
        _ciks_from_batch_row(payload)  # validate
        rows.append(payload)
    return rows


def build_remaining_cik_batches(
    batches: Iterable[Mapping[str, object]],
    done_batch_identities: set[str],
) -> list[dict[str, object]]:
    """Drop batches whose identity already has a done marker (Ticket 20 P0 resume)."""
    remaining: list[dict[str, object]] = []
    done = {str(item).lower() for item in done_batch_identities}
    for batch in batches:
        identity = batch_identity_for_ciks(_ciks_from_batch_row(batch))
        if identity in done:
            continue
        remaining.append(dict(batch))
    return remaining


def sanitize_accession_for_path(accession_number: str) -> str:
    """Filesystem/S3-safe accession segment (keeps digits, letters, . _ -)."""
    raw = str(accession_number or "").strip()
    if not raw:
        raise InventoryError("accession_number is empty")
    safe = re.sub(r"[^0-9A-Za-z._-]", "_", raw)
    if not safe or safe in {".", ".."}:
        raise InventoryError(f"invalid accession_number for path: {accession_number!r}")
    return safe


@dataclass(frozen=True)
class InsiderObservation:
    owner_cik: int | None
    owner_name: str
    issuer_cik: int
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool


def insider_inventory(db, ciks: Iterable[int] | None = None,
                      *, exclude_owner_ciks: Iterable[int] | None = None,
                      ) -> tuple[InsiderObservation, ...]:
    """Distinct insiders observed in silver ownership rows (Ticket 21 slice 1).

    One row per (owner identity, issuer) pair, deduped across filings: an
    insider filing ten Form 4s for the same issuer is one observation. Owner
    identity is owner_cik when present, else casefolded owner_name.
    ``exclude_owner_ciks`` removes corporate reporting owners (funds filing
    Form 4), mirroring _derive_is_insider's corporate skip.
    """
    cik_list = sorted({int(c) for c in (ciks or ())})
    where = ""
    params: list[int] = []
    if cik_list:
        where = f"WHERE issuer_cik IN ({', '.join('?' * len(cik_list))})"
        params = cik_list
    # duckdb-retirement-cutover Ticket 16 (2026-09-06): sec_company_filing
    # now widens to one row per (accession_number, cik) for a multi-CIK
    # accession -- without the inner QUALIFY below, a widened accession
    # would match twice (issuer's cik, and the reporting owner's own cik),
    # producing a bogus "insider of themselves" observation. The QUALIFY
    # prefers a candidate whose cik is NOT this row's own owner_cik,
    # falling back to whatever single match exists when that's the only
    # candidate.
    rows = db.fetch(
        f"""
        SELECT owner_cik, owner_name, issuer_cik,
               MAX(is_director) AS is_director,
               MAX(is_officer) AS is_officer,
               MAX(is_ten_percent_owner) AS is_ten_percent_owner
        FROM (
            SELECT o.accession_number, o.owner_index, o.owner_cik, o.owner_name,
                   CASE WHEN o.is_director THEN 1 ELSE 0 END AS is_director,
                   CASE WHEN o.is_officer THEN 1 ELSE 0 END AS is_officer,
                   CASE WHEN o.is_ten_percent_owner THEN 1 ELSE 0 END AS is_ten_percent_owner,
                   f.cik AS issuer_cik
            FROM sec_ownership_reporting_owner o
            JOIN sec_company_filing f ON o.accession_number = f.accession_number
            {prefer_non_owner_cik_qualify("o.accession_number, o.owner_index")}
        ) resolved
        {where}
        GROUP BY owner_cik, owner_name, issuer_cik
        """,
        params,
    )
    excluded = {int(c) for c in (exclude_owner_ciks or ())}
    seen: dict[tuple, InsiderObservation] = {}
    for row in rows:
        raw_cik = row.get("owner_cik")
        owner_cik = int(raw_cik) if raw_cik not in (None, "") else None
        name = str(row.get("owner_name") or "").strip()
        issuer = int(row.get("issuer_cik"))
        if owner_cik is not None and owner_cik in excluded:
            continue
        if owner_cik is None and not name:
            continue  # no usable identity at all
        key = (owner_cik if owner_cik is not None else name.casefold(), issuer)
        obs = InsiderObservation(
            owner_cik=owner_cik,
            owner_name=name,
            issuer_cik=issuer,
            is_director=bool(row.get("is_director")),
            is_officer=bool(row.get("is_officer")),
            is_ten_percent_owner=bool(row.get("is_ten_percent_owner")),
        )
        prior = seen.get(key)
        if prior is not None:
            obs = InsiderObservation(
                owner_cik=obs.owner_cik if obs.owner_cik is not None else prior.owner_cik,
                owner_name=obs.owner_name or prior.owner_name,
                issuer_cik=issuer,
                is_director=obs.is_director or prior.is_director,
                is_officer=obs.is_officer or prior.is_officer,
                is_ten_percent_owner=obs.is_ten_percent_owner or prior.is_ten_percent_owner,
            )
        seen[key] = obs
    return tuple(sorted(
        seen.values(),
        key=lambda o: (o.issuer_cik, o.owner_cik if o.owner_cik is not None else -1,
                       o.owner_name.casefold()),
    ))


def partition_insider_coverage(
    inventory: Iterable[InsiderObservation],
    *,
    resolve_person,        # (owner_cik, owner_name) -> person_id | None
    resolve_issuer,        # (issuer_cik) -> issuer_entity_id | None
    has_insider_version,   # (person_id, issuer_entity_id) -> bool
) -> dict[str, object]:
    """Ticket 21 slice 2: partition observed insiders into identified vs
    unresolved against MDM. Identified means the person resolves to exactly
    one MDM entity AND carries an IS_INSIDER version to the resolved issuer.
    Fail-closed consumers require unresolved == []. Resolver callables are
    injected so this is testable without an MDM connection."""
    identified: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    for obs in inventory:
        record: dict[str, object] = {
            "owner_cik": obs.owner_cik,
            "owner_name": obs.owner_name,
            "issuer_cik": obs.issuer_cik,
        }
        person_id = resolve_person(obs.owner_cik, obs.owner_name)
        if person_id is None:
            unresolved.append({**record, "reason": "unresolved_person"})
            continue
        issuer_id = resolve_issuer(obs.issuer_cik)
        if issuer_id is None:
            unresolved.append({**record, "reason": "unresolved_issuer"})
            continue
        if not has_insider_version(person_id, issuer_id):
            unresolved.append({**record, "reason": "missing_is_insider_version"})
            continue
        identified.append(record)
    return {
        "insider_total": len(identified) + len(unresolved),
        "insider_identified": len(identified),
        "insider_unresolved": len(unresolved),
        "unresolved": unresolved,
        "source": "sec_ownership_reporting_owner",
    }

"""Profiling ticket 04c trial: every GLEIF Level 1 record naming a successor,
read by the real GLEIF reader (`record_evidence`) with the new contract.

Local Golden Copy of 2026-09-11 only; no request to any provider. Each record is
read as in scope (its own LEI eligible), so the reading is tested, not scope.
Writes RESULT.json beside this file: counts and up to 8 examples.

    uv run --extra mdm --with ijson python .scratch/profiling/trials/gleif-successor/run.py <lei2 zip>
"""

import collections
import json
import sys
import time
import zipfile
from pathlib import Path

import ijson

from edgar_warehouse.mdm.clean.evidence import instant
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

contract = dataset_contract("level1")
publication = {"publication_key": "gleif-20260911-1600", "revision": 1, "artifact_sha256": "0" * 64, "member": "level1"}
counts, kinds, examples = collections.Counter(), collections.Counter(), []
without_event, bad_dates = collections.Counter(), []
started = time.time()
archive = zipfile.ZipFile(sys.argv[1])
with archive.open(archive.namelist()[0]) as f:
    for ordinal, record in enumerate(ijson.items(f, "records.item", use_float=True)):
        successors = (record.get("Entity") or {}).get("SuccessorEntity")
        if not successors:
            continue
        counts["records_with_successor"] += 1
        with_lei = sum(1 for s in successors if (s.get("SuccessorLEI") or {}).get("$"))
        counts["successor_leis"] += with_lei
        counts["successors_named_only"] += len(successors) - with_lei
        outcome, evidence = record_evidence(record, member="level1", contract=contract, source_code="gleif.level1.v1",
                                            eligible_leis={record["LEI"]["$"]}, publication=publication,
                                            ordinal=ordinal)
        counts[f"outcome_{outcome}"] += 1
        if outcome != "assertion":
            kinds[f"deferred:{evidence['reason']}"] += 1
            continue
        links = evidence["relationships"]
        counts["links"] += len(links)
        events = (record["Entity"].get("LegalEntityEvents") or {}).get("LegalEntityEvent") or []
        events = events if isinstance(events, list) else [events]
        leis = [s["SuccessorLEI"]["$"] for s in successors if (s.get("SuccessorLEI") or {}).get("$")]
        for link, lei in zip(links, leis):
            def affected(event):
                fields = (event.get("AffectedFields") or {}).get("AffectedField") or []
                return {f.get("$") for f in (fields if isinstance(fields, list) else [fields]) if isinstance(f, dict)}
            naming = [e for e in events if lei in affected(e)]
            completed = [e for e in naming if e.get("@event_status") == "COMPLETED"]
            if len(completed) > 1:
                counts["links_with_several_completed_events"] += 1
                if len({(e.get("LegalEntityEventEffectiveDate") or {}).get("$") for e in completed}) > 1:
                    counts["links_with_several_completed_events_on_different_dates"] += 1
            dated = link["valid_from"] is not None
            counts["links_dated" if dated else "links_first_seen"] += 1
            kinds[link["properties"]["source_event_type"] or "no completed event"] += 1
            if dated:
                try:
                    instant(link["valid_from"])
                except (ValueError, TypeError):
                    bad_dates.append(link["valid_from"])
            else:
                other = sorted({f"{e.get('@event_status')} {(e.get('LegalEntityEventType') or {}).get('$')}"
                                for e in naming}) or ["no event names it"]
                without_event[f"entity {link['properties']['source_entity_status']}; " + ", ".join(other)] += 1
        if len(links) != with_lei:
            counts["records_links_differ_from_leis"] += 1
        shape = (len(successors) > 1, with_lei < len(successors), any(link["valid_from"] is None for link in links))
        if shape not in {e["shape"] for e in examples} and len(examples) < 8:
            examples.append({"shape": shape, "lei": record["LEI"]["$"],
                             "successors": successors, "links": [
                                 {k: link[k] for k in ("type", "valid_from", "properties")} for link in links]})
for e in examples:
    several, named_only, undated = e.pop("shape")
    e["shows"] = [w for w, on in (("several successors", several), ("a successor named only", named_only),
                                  ("no completed event naming it", undated)) if on] or ["one dated successor"]
result = {"source": "GLEIF Golden Copy 2026-09-11 16:00, Level 1 (local capture)", "counts": counts,
          "links_by_event_type": dict(kinds.most_common()),
          "links_with_no_completed_event": dict(without_event.most_common()),
          "dates_that_do_not_parse": bad_dates[:20], "dates_that_do_not_parse_count": len(bad_dates),
          "examples": examples,
          "seconds": round(time.time() - started)}
(Path(__file__).parent / "RESULT.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
print(json.dumps({k: result[k] for k in ("counts", "links_by_event_type", "links_with_no_completed_event",
                                         "dates_that_do_not_parse_count")}, indent=1))

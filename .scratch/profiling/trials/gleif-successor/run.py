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

from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence

contract = dataset_contract("level1")
publication = {"publication_key": "gleif-20260911-1600", "revision": 1, "artifact_sha256": "0" * 64, "member": "level1"}
counts, kinds, examples = collections.Counter(), collections.Counter(), []
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
        for link in links:
            dated = link["valid_from"] is not None
            counts["links_dated" if dated else "links_first_seen"] += 1
            kinds[link["properties"]["source_event_type"] or "no completed event"] += 1
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
          "links_by_event_type": dict(kinds.most_common()), "examples": examples,
          "seconds": round(time.time() - started)}
(Path(__file__).parent / "RESULT.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
print(json.dumps({"counts": counts, "links_by_event_type": dict(kinds.most_common())}, indent=1))

"""Peak memory and time of the receipt's keys: the old set against KeySet, on invented keys of a holding's shape.

    PYTHONPATH=. python scripts/dev/bench_silver_keys.py set 3000000
    PYTHONPATH=. python scripts/dev/bench_silver_keys.py keyset 3000000

Both print the same digest; the peak is ru_maxrss of the process."""
import hashlib
import json
import resource
import sys
import time
mode, n = sys.argv[1], int(sys.argv[2])
def rows():  # invented holdings: an accession and a holding id per row, like nport_holding's key
    for i in range(n):
        yield (f"0001234567-26-{i // 200:06d}", f"holding-{i % 200:05d}")
t=time.time()
if mode == "set":
    seen = set(); seen.update(rows())
    digest = hashlib.sha256(json.dumps(sorted(seen), separators=(",", ":")).encode()).hexdigest(); count = len(seen)
else:
    from edgar_warehouse.silver_writer.keyset import KeySet
    with KeySet() as seen:
        seen.add(rows()); count, digest = seen.summary()
print(f"{mode:7} {n:>9,} keys  peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576:7.0f} MB  {time.time()-t:5.1f} s  {digest[:12]}")

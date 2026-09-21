"""PROTOTYPE — what the runner's network guard does and does not cover (check 4).

(a) Python sockets to an outside host: refused before any packet is sent.
(b) Python sockets to loopback: refused until the merge harness allows it.
(c) psycopg2 → libpq opens its socket in C, below the Python guard. We try a
    non-routable private address (10.255.255.1, nothing answers) with a 2 s
    timeout: a *timeout* means libpq really tried the network; a RuntimeError
    would mean the guard caught it.
"""

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import source_engine as se  # noqa: E402

results = {}
try:
    import urllib.request
    urllib.request.urlopen("http://example.com", timeout=2)
    results["a_python_outside"] = "CONNECTED (guard failed)"
except Exception as e:
    results["a_python_outside"] = f"refused: {type(e).__name__}: {str(e)[:70]}"

s = socket.socket()
try:
    s.connect(("127.0.0.1", 9))
    results["b_loopback_default"] = "connected"
except Exception as e:
    results["b_loopback_default"] = f"refused: {type(e).__name__}: {str(e)[:70]}"
finally:
    s.close()
se.LOOPBACK_ALLOWED = True
s = socket.socket()
try:
    s.connect(("127.0.0.1", 9))
    results["b_loopback_allowed"] = "connected"
except ConnectionRefusedError:
    results["b_loopback_allowed"] = "passed the guard (nothing listens on :9, as expected)"
except Exception as e:
    results["b_loopback_allowed"] = f"{type(e).__name__}: {str(e)[:70]}"
finally:
    s.close()
se.LOOPBACK_ALLOWED = False

try:
    import psycopg2
    psycopg2.connect(host="10.255.255.1", dbname="x", user="x", password="x", connect_timeout=2)
    results["c_libpq_outside"] = "CONNECTED"
except RuntimeError as e:
    results["c_libpq_outside"] = f"caught by the Python guard: {e}"
except Exception as e:
    results["c_libpq_outside"] = f"BYPASSED the Python guard — libpq tried the network: {type(e).__name__}: {str(e).strip()[:80]}"

for k, v in results.items():
    print(f"{k:22} {v}")

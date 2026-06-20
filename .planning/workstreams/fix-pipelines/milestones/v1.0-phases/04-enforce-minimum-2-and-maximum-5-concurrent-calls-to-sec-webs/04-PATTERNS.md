# Phase 04: SEC Rate Limiting - Pattern Map

**Mapped:** 2026-05-16
**Files analyzed:** 3
**Analogs found:** 1 / 3

---

## IMPORTANT: Default Value Mismatch — Planner Must Resolve

CONTEXT.md D-02 says "change `BOOTSTRAP_BATCH_CONCURRENCY` default from 10 → 5."
The **actual current value** in `infra/scripts/deploy-aws-application.sh` line 139 is **3**, not 10.

Changing 3 → 5 is a **raise** in concurrency, not a cap. The planner must confirm with the
user before making this change:

- If the intent is "cap at 5 for SEC safety," the current value of 3 is already within the
  recommended range and the change may be unnecessary.
- If the intent is "set to exactly 5 as the standard default," then 3 → 5 is valid but the
  reason in the commit message should be "set default to 5" not "reduce from 10."

Do not apply this change without explicit user confirmation of the direction.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `edgar_warehouse/infrastructure/sec_client.py` | utility (HTTP client) | request-response | `.venv/lib/python3.12/site-packages/edgar/httpclient.py` lines 145–161 + `.venv/lib/python3.12/site-packages/httpxthrottlecache/ratelimiter.py` lines 14–29 | role-match (only analog; no in-house usage exists) |
| `infra/scripts/deploy-aws-application.sh` | config/deploy script | n/a | itself — in-place edit of line 139 | in-place edit |
| `CLAUDE.md` | documentation | n/a | itself — additive note to "Phased Pipeline" section | in-place edit |

---

## Pattern Assignments

### `edgar_warehouse/infrastructure/sec_client.py` (utility, request-response)

**Analog:** `.venv/lib/python3.12/site-packages/edgar/httpclient.py` (edgartools library)
and `.venv/lib/python3.12/site-packages/httpxthrottlecache/ratelimiter.py`

No in-house code uses `pyrate_limiter` — confirmed by grep across all of
`edgar_warehouse/`, `scripts/`, and `infra/` (no matches). The only patterns are from the
vendored edgartools library.

**Step 1 — Build a Limiter (construction pattern)**

Source: `.venv/lib/python3.12/site-packages/edgar/httpclient.py` lines 145–161

```python
from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate

def _create_rate_limiter(requests_per_second: int):
    """Create a rate limiter compatible with both pyrate-limiter 3.x and 4.x.

    pyrate-limiter 4.0 removed max_delay, raise_when_fail, and retry_until_max_delay
    parameters from Limiter.__init__(). This function handles both API versions.
    """
    rate = Rate(requests_per_second, Duration.SECOND)
    bucket = InMemoryBucket([rate])
    try:
        # pyrate-limiter 3.x API
        return Limiter(bucket, max_delay=Duration.DAY, raise_when_fail=False, retry_until_max_delay=True)
    except TypeError:
        # pyrate-limiter 4.0+ removed these parameters
        return Limiter(bucket)
```

**IMPORTANT NOTE:** The lockfile resolves `pyrate-limiter==4.1.0`. The 4.x branch
constructor **does not accept** `max_delay`, `raise_when_fail`, or `retry_until_max_delay`.
The `try/except TypeError` above is the safe multi-version guard edgartools uses.
For our code targeting the locked 4.1.0 only, a direct `Limiter(bucket)` (the except
branch) is sufficient, but the try/except guard is harmless and future-safe. Use whichever
the planner prefers; both are correct.

**Simpler 4.x-only form** (httpxthrottlecache ratelimiter.py lines 14–16):

```python
from pyrate_limiter import Duration, Limiter, Rate

def create_rate_limiter(requests_per_second: int) -> Limiter:
    rate = Rate(requests_per_second, Duration.SECOND)
    return Limiter(rate)
```

Note: `Limiter(rate)` (pass Rate directly) is valid in 4.x; `InMemoryBucket([rate])` is
also valid. Both produce equivalent behavior.

**Step 2 — Module-level singleton (where to declare it)**

The edgartools analog uses an eager module-level constant (httpclient.py line 323):

```python
HTTP_MGR = get_http_mgr(request_per_sec_limit=get_edgar_rate_limit_per_sec())
```

**Use the same eager pattern** in `sec_client.py` — add the imports at the top of the file
and declare the singleton at module scope (after the helper function definition):

```python
# At top of file, with other imports:
from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate

def _create_sec_rate_limiter() -> Limiter:
    rate = Rate(9, Duration.SECOND)
    bucket = InMemoryBucket([rate])
    try:
        return Limiter(bucket, max_delay=Duration.DAY, raise_when_fail=False, retry_until_max_delay=True)
    except TypeError:
        return Limiter(bucket)

# Module-level singleton — created once at import time, shared by all calls
# in this process. Does NOT coordinate across ECS tasks.
_SEC_RATE_LIMITER: Limiter = _create_sec_rate_limiter()
```

The `sec_client.py` file defers `import httpx` inside `download_sec_bytes()` to avoid
import-time side effects. However, `pyrate_limiter` has no side effects at import — eager
init is appropriate and matches the edgartools pattern directly.

**Step 3 — Call-site: how to acquire a rate token**

Source: `.venv/lib/python3.12/site-packages/httpxthrottlecache/ratelimiter.py` lines 27–28

```python
# Inside RateLimitingTransport.handle_request():
self.limiter.try_acquire(__name__)
```

`try_acquire` signature (pyrate_limiter 4.1.0, limiter.py line 301):

```python
def try_acquire(
    self,
    name: str = "pyrate",
    weight: int = 1,
    blocking: bool = True,   # default True — BLOCKS until token available
    timeout: int | float = -1,  # -1 = block indefinitely
) -> Union[bool, Awaitable[bool]]:
```

With `blocking=True` (the default), `try_acquire` **blocks** the calling thread until a
token is available — it does not raise and does not skip. This is the correct behavior for
`download_sec_bytes()`: we want to throttle, not drop requests.

**Exact insertion point in `download_sec_bytes()`:**

The token acquire must happen **before the retry loop**, once per logical SEC request (not
once per retry attempt). Insert after the existing validation call:

```python
def download_sec_bytes(url: str, identity: str) -> bytes:
    import httpx

    _validate_sec_url(url)
    # --- ADD HERE ---
    _SEC_RATE_LIMITER.try_acquire("sec_download")  # blocks until rate slot available
    # --- END ADD ---
    last_error: Exception | None = None
    headers = {"Accept": "*/*", "User-Agent": identity}
    ...
    for attempt in range(1, 4):
        ...
```

Placing the acquire before the loop means: one token consumed per `download_sec_bytes()`
call regardless of how many retry attempts occur. This matches the intent (limit SEC
requests, not retry delay cycles).

---

## Shared Patterns

None that cross multiple files in this phase. The rate limiter is isolated to
`sec_client.py`.

---

## No Analog Found (In-Place Edits)

### `infra/scripts/deploy-aws-application.sh`

**Role:** deploy configuration
**Change:** One-line default value edit + inline comment update
**No analog needed.** The pattern is the existing line itself.

Exact location: line 139

```bash
BOOTSTRAP_BATCH_CONCURRENCY=3   # current value — see mismatch note above
```

Target state (after user confirms direction):

```bash
BOOTSTRAP_BATCH_CONCURRENCY=5  # SEC rate limit: keep between 2–5 for production
```

Also add an inline comment near the `--bootstrap-batch-concurrency` flag (line 188) to note
the recommended range.

**Do NOT tighten the regex at line 209** (`[[ ... =~ ^[1-9][0-9]*$ ]]`). CONTEXT.md D-02
and D-05 explicitly prohibit hard validation enforcement — the floor is documentation-only.
Only add a comment above line 209 if useful; leave the regex unchanged.

**REMINDER TO PLANNER:** Verify with the user whether 3 → 5 is intended before committing.

### `CLAUDE.md`

**Role:** documentation
**Change:** Additive note to the "Phased Pipeline" section
**No analog needed.** Append or insert the following note near the
`BOOTSTRAP_BATCH_CONCURRENCY` variable description in the "Phased Pipeline" section:

```
**`BOOTSTRAP_BATCH_CONCURRENCY` recommended range: 2–5.**
Values below 2 are not recommended for production — throughput is too low.
Values above 5 risk triggering SEC rate limiting (10 req/sec per IP; 5 tasks × ~9 req/sec
theoretical max = 45 req/sec, well above the limit without stagger mitigation).
```

---

## Metadata

**Analog search scope:** `edgar_warehouse/`, `scripts/`, `infra/` (Python files only);
`.venv/lib/python3.12/site-packages/edgar/httpclient.py`;
`.venv/lib/python3.12/site-packages/httpxthrottlecache/ratelimiter.py`
**Files scanned:** ~6 targeted reads
**Pattern extraction date:** 2026-05-16

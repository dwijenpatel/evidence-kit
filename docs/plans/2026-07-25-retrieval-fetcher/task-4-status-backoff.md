# Task 4 — status backoff: 403 as a rate-limit signal

**Tier:** `code-complete` · **PRD criteria:** A4

Pure functions, no framework coupling — the retry *decision* is separable from the retry
*mechanism*, and separating it is what makes it testable without a network or a crawl.

## Why 403 is here

RFC 9110 §15.5.4 defines 403 as "the server understood the request but refuses to fulfill
it." It does **not** say permanent, and it does not say retrying is futile — that reading is
a common but unstated inference. Commercial WAFs (Cloudflare, Akamai) routinely return 403
rather than 429 for rate-limit and bot-detection triggers.

This is the error that put a false absence into the corpus: an agent recorded a hard 403
across ten hosts, and a single polite request to the same host returned 200.

## Files

| Path | Responsibility |
|---|---|
| `fetcher/evidence_fetch/backoff.py` (new) | `parse_retry_after`, `backoff_delay`, `classify_status` |
| `fetcher/tests/test_backoff.py` (new) | Tests |

## Provides

```python
def parse_retry_after(value: str | None, now: datetime) -> float | None
    """Seconds to wait, from either Retry-After form. None if absent/unparseable.
    Never negative: an HTTP-date in the past yields 0.0."""

def backoff_delay(attempt: int, base: float = 1.0, cap: float = 60.0,
                  rand: Callable[[], float] = random.random) -> float
    """Full jitter: uniform in [0, min(cap, base * 2 ** attempt)]. attempt is
    0-based. Raises ValueError if attempt < 0."""

class Disposition(enum.Enum):
    RETRY = "retry"        # transient; back off and try again
    BLOCKED = "blocked"    # persistent after backoff at reduced pace
    OK = "ok"
    FATAL = "fatal"        # 404/410 and other permanent client errors

def classify_status(status: int, attempt: int, max_attempts: int = 3) -> Disposition
    """attempt is 0-BASED — the same convention as backoff_delay. The manifest's
    1-based attempt_n is converted once at the call site: zero_based = attempt_n - 1,
    passed to BOTH functions (task 6 pins this)."""
```

## Behaviour, pinned

`classify_status`:

| Status | attempt < max_attempts | attempt ≥ max_attempts |
|---|---|---|
| 200–299 | `OK` | `OK` |
| **403** | **`RETRY`** | `BLOCKED` |
| 429 | `RETRY` | `BLOCKED` |
| 503, 502, 504, 500, 408, 522, 524 | `RETRY` | `BLOCKED` |
| 404, 410 | `FATAL` | `FATAL` |
| other 4xx | `FATAL` | `FATAL` |
| 3xx | `OK` | `OK` |

**This does NOT mean a `BLOCKED` verdict writes anything into the corpus.** `BLOCKED` is a
statement about a fetch attempt sequence, never about the world. Per CLAUDE.md rule 15 each
attempt is already its own manifest entry; a `BLOCKED` disposition adds no new record and
authorises no absence claim. The distinction is the entire point of the task.

`parse_retry_after` worked examples, with `now = 2026-07-25T12:00:00Z`:

| Header value | Returns |
|---|---|
| `"120"` | `120.0` |
| `"0"` | `0.0` |
| `"Sat, 25 Jul 2026 12:02:00 GMT"` | `120.0` |
| `"Sat, 25 Jul 2026 11:58:00 GMT"` | `0.0` (past → clamp, never negative) |
| `None` | `None` |
| `"soon"` | `None` |
| `"-5"` | `0.0` |

`backoff_delay` worked examples with `rand=lambda: 1.0` (upper bound) and defaults:

| attempt | Returns |
|---|---|
| 0 | 1.0 |
| 1 | 2.0 |
| 2 | 4.0 |
| 6 | 60.0 (capped) |

With `rand=lambda: 0.0` every row returns `0.0`. **Full jitter draws from `[0, ceiling]`,
not `ceiling ± jitter`** — the point is spreading retries across clients, and the
half-jitter variants measurably cluster worse.

## Step 1 — failing tests

`fetcher/tests/test_backoff.py`:

```python
import unittest
from datetime import datetime, timezone

from evidence_fetch.backoff import (Disposition, backoff_delay, classify_status,
                                    parse_retry_after)

NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)


class RetryAfterTests(unittest.TestCase):
    def test_seconds_form(self):
        self.assertEqual(parse_retry_after("120", NOW), 120.0)

    def test_http_date_form(self):
        self.assertEqual(
            parse_retry_after("Sat, 25 Jul 2026 12:02:00 GMT", NOW), 120.0)

    def test_past_date_clamps_to_zero(self):
        self.assertEqual(
            parse_retry_after("Sat, 25 Jul 2026 11:58:00 GMT", NOW), 0.0)

    def test_negative_seconds_clamp_to_zero(self):
        self.assertEqual(parse_retry_after("-5", NOW), 0.0)

    def test_absent_and_garbage_are_none(self):
        self.assertIsNone(parse_retry_after(None, NOW))
        self.assertIsNone(parse_retry_after("soon", NOW))


class BackoffTests(unittest.TestCase):
    def test_full_jitter_upper_bound_doubles(self):
        hi = lambda: 1.0
        self.assertEqual([backoff_delay(a, rand=hi) for a in range(4)],
                         [1.0, 2.0, 4.0, 8.0])

    def test_capped(self):
        self.assertEqual(backoff_delay(6, rand=lambda: 1.0), 60.0)

    def test_lower_bound_is_zero(self):
        self.assertEqual(backoff_delay(3, rand=lambda: 0.0), 0.0)

    def test_negative_attempt_rejected(self):
        with self.assertRaises(ValueError):
            backoff_delay(-1)


class ClassifyTests(unittest.TestCase):
    def test_403_is_retryable_before_exhaustion(self):
        self.assertIs(classify_status(403, attempt=0), Disposition.RETRY)

    def test_403_becomes_blocked_only_after_exhaustion(self):
        self.assertIs(classify_status(403, attempt=3), Disposition.BLOCKED)

    def test_429_and_503_are_retryable(self):
        for s in (429, 503):
            self.assertIs(classify_status(s, attempt=0), Disposition.RETRY)

    def test_404_is_fatal_immediately(self):
        self.assertIs(classify_status(404, attempt=0), Disposition.FATAL)

    def test_success_is_ok(self):
        self.assertIs(classify_status(200, attempt=0), Disposition.OK)
```

Run: `uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q`
→ `ModuleNotFoundError: No module named 'evidence_fetch.backoff'`.

## Step 2 — implementation

`fetcher/evidence_fetch/backoff.py`:

```python
"""Retry decisions, separated from retry mechanism so they are testable alone.

The load-bearing choice here is that 403 is retryable. RFC 9110 §15.5.4 says only
that the server "refuses to fulfill" the request; permanence is an inference the
spec does not license, and WAFs emit 403 for rate limiting. Reading a first 403 as
a permanent block is what put a false absence into the corpus.
"""

import enum
import random
from collections.abc import Callable
from datetime import datetime
from email.utils import parsedate_to_datetime

RETRYABLE = frozenset({403, 408, 429, 500, 502, 503, 504, 522, 524})
FATAL = frozenset({400, 401, 404, 405, 410, 451})


class Disposition(enum.Enum):
    OK = "ok"
    RETRY = "retry"
    BLOCKED = "blocked"
    FATAL = "fatal"


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    """Seconds to wait, from either RFC 9110 §10.2.3 form. None if unusable."""
    if value is None:
        return None
    value = value.strip()
    try:
        return max(0.0, float(int(value)))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, (when - now).total_seconds())


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 60.0,
                  rand: Callable[[], float] = random.random) -> float:
    """Full jitter: uniform in [0, min(cap, base * 2**attempt)].

    Full jitter rather than a jittered constant: capped exponential backoff alone
    still produces synchronised retry clusters across clients.
    """
    if attempt < 0:
        raise ValueError(f"attempt must be >= 0, got {attempt}")
    ceiling = min(cap, base * (2 ** attempt))
    return rand() * ceiling


def classify_status(status: int, attempt: int,
                    max_attempts: int = 3) -> Disposition:
    """Disposition for one attempt. `attempt` is 0-based, matching backoff_delay;
    the manifest's 1-based attempt_n is converted by the caller. BLOCKED is a claim
    about this attempt sequence, never about the world — it authorises no absence
    finding."""
    if 200 <= status < 400:
        return Disposition.OK
    if status in RETRYABLE:
        return Disposition.RETRY if attempt < max_attempts else Disposition.BLOCKED
    return Disposition.FATAL
```

Note `float(int(value))` rather than `float(value)`: RFC 9110's delay-seconds form is an
integer, and accepting `"1.5e3"` would silently diverge from what the header can mean.

Re-run → 14 pass.

## Error model

No exceptions escape except `ValueError` from `backoff_delay` on a negative attempt. Every
parse failure returns `None`, because a malformed `Retry-After` must degrade to "use our own
backoff", never to a crash mid-crawl.

## Checks

```
test -f fetcher/evidence_fetch/backoff.py
grep -qE '^RETRYABLE = frozenset' fetcher/evidence_fetch/backoff.py
grep -qF 'test_429_and_503_are_retryable' fetcher/tests/test_backoff.py
grep -qF 'test_403_is_retryable_before_exhaustion' fetcher/tests/test_backoff.py
grep -qF 'test_403_becomes_blocked_only_after_exhaustion' fetcher/tests/test_backoff.py
grep -qF 'test_past_date_clamps_to_zero' fetcher/tests/test_backoff.py
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
```

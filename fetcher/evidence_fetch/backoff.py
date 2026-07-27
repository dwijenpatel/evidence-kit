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


FAILURE_CLASSES = ("dns-failure", "connection-refused", "timeout", "tls-error",
                   "robots-disallowed", "other")

_FAILURE_BY_EXC = {
    # scrapy 2.17.0 wraps twisted's transport errors in scrapy.exceptions.* — these
    # names were probed live (dns-dead host, closed port, DOWNLOAD_TIMEOUT against a
    # slow handler). The bare twisted names are kept as aliases in case a future
    # scrapy stops wrapping.
    "CannotResolveHostError": "dns-failure",
    "DNSLookupError": "dns-failure",
    "DownloadConnectionRefusedError": "connection-refused",
    "ConnectionRefusedError": "connection-refused",
    "DownloadTimeoutError": "timeout",
    "TimeoutError": "timeout",
    "TCPTimedOutError": "timeout",
}


def failure_class_for(exc_type_name: str, detail: str = "") -> str:
    """Failure class for an exception type name plus its message.

    String-keyed on purpose: importing twisted or scrapy types here would couple the
    one pure-decision module to the framework (rule: this file stays import-light and
    testable bare). The recorder passes type(exc).__name__ and str(exc).
    """
    if exc_type_name == "IgnoreRequest" and "robots" in detail.lower():
        return "robots-disallowed"
    if exc_type_name == "DownloadFailedError" and "ssl" in detail.lower():
        return "tls-error"      # probed: the OpenSSL text rides in the message
    return _FAILURE_BY_EXC.get(exc_type_name, "other")


def classify_failure(failure_class: str, attempt: int,
                     max_attempts: int = 3) -> Disposition:
    """Disposition for a no-response attempt (`attempt` 0-based, as classify_status).

    robots-disallowed is BLOCKED immediately — a policy answer, not transience;
    re-asking is a fresh robots fetch on a later run, not a retry. Everything else,
    including "other", retries then blocks: an unclassified death is not evidence of
    permanence.
    """
    if failure_class == "robots-disallowed":
        return Disposition.BLOCKED
    return Disposition.RETRY if attempt < max_attempts else Disposition.BLOCKED

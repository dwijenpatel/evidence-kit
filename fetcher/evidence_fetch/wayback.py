"""Wayback URL construction and CDX parsing. No network code lives here — a capture
URL is fetched by the ordinary spider path, and CDX responses arrive as cached bytes."""

import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode

EMPTY_SHA1 = "3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ"   # base32 SHA-1 of b"": nothing captured
TS14 = re.compile(r"^\d{14}$")
CDX_BASE = "https://web.archive.org/cdx/search/cdx"
FIELDS = "timestamp,digest,statuscode"


def capture_url(timestamp: str, original_url: str) -> str:
    """Replay URL returning ORIGINAL bytes (the id_ modifier), scheme included."""
    if not TS14.match(timestamp):
        raise ValueError(f"need a 14-digit timestamp, got {timestamp!r}")
    return f"https://web.archive.org/web/{timestamp}id_/{original_url}"


def cdx_query_url(url: str, *, from_ts: str | None = None, to_ts: str | None = None,
                  collapse_digest: bool = True, limit: int | None = None) -> str:
    """CDX search URL. Parameter order is pinned: url, output, fl, from, to,
    collapse, limit — so the string is stable and testable."""
    params = [("url", url), ("output", "json"), ("fl", FIELDS)]
    if from_ts is not None:
        params.append(("from", from_ts))
    if to_ts is not None:
        params.append(("to", to_ts))
    if collapse_digest:
        params.append(("collapse", "digest"))
    if limit is not None:
        params.append(("limit", str(limit)))
    return f"{CDX_BASE}?{urlencode(params)}"


@dataclass(frozen=True)
class Capture:
    timestamp: str      # 14 digits
    digest: str         # base32 SHA-1, as CDX reports it
    status: str         # CDX statuscode — a STRING, may be "-" for unknown


def parse_cdx(body: bytes) -> list[Capture]:
    """CDX JSON -> Captures. Row 0 is the header row and is dropped. An empty body
    AND an empty JSON array both mean "no captures" and return [] — CDX sends the
    former for never-archived URLs, and treating either as an error would turn
    "never archived" into a crash."""
    if not body.strip():
        return []
    try:
        rows = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"not valid CDX JSON: {e}") from e
    if not isinstance(rows, list):
        raise ValueError("not valid CDX JSON: top level is not a list")
    captures = []
    for i, row in enumerate(rows[1:], start=1):
        if not isinstance(row, list) or len(row) < 3:
            raise ValueError(f"CDX row {i}: expected 3 fields, got {row!r}")
        captures.append(Capture(str(row[0]), str(row[1]), str(row[2])))
    return captures


def distinct_digests(captures: list[Capture]) -> list[str]:
    """All digests, first-appearance order, deduplicated globally — CDX's own
    collapse=digest is adjacent-only and over-reports change ~8x (measured)."""
    seen: set[str] = set()
    out: list[str] = []
    for c in captures:
        if c.digest not in seen:
            seen.add(c.digest)
            out.append(c.digest)
    return out


def content_digests(captures: list[Capture]) -> list[str]:
    """Digests of retrievable content only: status "200", never EMPTY_SHA1."""
    return distinct_digests([c for c in captures
                             if c.status == "200" and c.digest != EMPTY_SHA1])

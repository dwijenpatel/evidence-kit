"""The per-attempt manifest: one JSON object per line, append-only.

The manifest is the seam the change-detection half consumes. `append_entry`
validates the fetcher schema (schema 1, exactly 23 keys); `load_prior_index`
tolerates other producers' lines, because the file is shared and append-only —
a line is a fetcher line iff it carries BOTH `schema` and `url_requested`.
"""

import json
import os

from evidence_fetch.backoff import FAILURE_CLASSES

REQUIRED_KEYS = frozenset({
    "schema", "url_requested", "url_final", "attempt_n", "fetched_at",
    "http_status", "response_protocol", "raw_bytes_sha256", "raw_bytes_length",
    "cache_relpath", "content_type", "request_headers", "response_headers",
    "redirect_chain", "etag", "etag_is_weak", "last_modified", "disposition",
    "fetch_policy", "useragent_sent", "prior_fetch_ref", "seed_signal", "failure",
})

FETCH_POLICY_KEYS = frozenset(
    {"delay_used_s", "robots_url", "robots_sha256", "robots_fetched_at"})

# Null as a block exactly when `failure` is non-null: nothing was received, so
# nothing about a response may be asserted.
RESPONSE_UNIT_KEYS = frozenset({
    "http_status", "response_protocol", "raw_bytes_sha256", "raw_bytes_length",
    "cache_relpath", "content_type", "response_headers", "etag", "etag_is_weak",
    "last_modified",
})


class ManifestSchemaError(ValueError):
    """The entry (or an existing fetcher line) violates the pinned schema."""


def _validate(entry: dict) -> None:
    missing = REQUIRED_KEYS - entry.keys()
    if missing:
        raise ManifestSchemaError(
            f"missing required key(s): {sorted(missing)}")
    unknown = entry.keys() - REQUIRED_KEYS
    if unknown:
        raise ManifestSchemaError(f"unknown key(s): {sorted(unknown)}")

    policy = entry["fetch_policy"]
    if not isinstance(policy, dict) or policy.keys() != FETCH_POLICY_KEYS:
        raise ManifestSchemaError(
            f"fetch_policy must have exactly {sorted(FETCH_POLICY_KEYS)}, "
            f"got: {policy!r}")

    failure = entry["failure"]
    if (entry["http_status"] is None) != (failure is not None):
        raise ManifestSchemaError(
            "failure XOR violated: `failure` must be non-null exactly when "
            f"`http_status` is null (failure={failure!r}, "
            f"http_status={entry['http_status']!r})")
    if failure is not None:
        non_null = sorted(k for k in RESPONSE_UNIT_KEYS if entry[k] is not None)
        if non_null:
            raise ManifestSchemaError(
                f"failure line carries non-null response-unit field(s): {non_null}")
        if not isinstance(failure, dict) or failure.keys() != {"class", "detail"}:
            raise ManifestSchemaError(
                f"failure must be exactly {{class, detail}}, got: {failure!r}")
        if failure["class"] not in FAILURE_CLASSES:
            raise ManifestSchemaError(
                f"failure class {failure['class']!r} not in {FAILURE_CLASSES}")


def append_entry(manifest_path: str, entry: dict) -> None:
    """Serialise one entry as a single JSON line and append, fsync'd."""
    _validate(entry)
    line = json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n"
    with open(manifest_path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def load_prior_index(manifest_path: str) -> dict[str, str]:
    """url_requested -> raw_bytes_sha256 of its most recent 2xx entry.

    "Most recent" means last matching line in FILE ORDER — `fetched_at` is never
    consulted (append order is the authority; the two can diverge under
    concurrency and after a git merge). Returns {} when the manifest does not
    exist. A trailing partial line is ignored, not an error.
    """
    if not os.path.exists(manifest_path):
        return {}
    with open(manifest_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    index: dict[str, str] = {}
    last = len(lines) - 1
    for i, raw in enumerate(lines):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            if i == last:
                continue    # a crash mid-append leaves a partial final line
            raise ManifestSchemaError(
                f"corrupt manifest line {i + 1}: {raw[:80]!r}") from None
        # A fetcher line carries BOTH keys; anything else is another
        # producer's, not corruption.
        if not isinstance(entry, dict) or \
                "schema" not in entry or "url_requested" not in entry:
            continue
        if entry["schema"] != 1:
            raise ManifestSchemaError(
                f"unknown schema version {entry['schema']!r} on line {i + 1}")
        status = entry.get("http_status")
        if isinstance(status, int) and 200 <= status < 300:
            index[entry["url_requested"]] = entry["raw_bytes_sha256"]
    return index

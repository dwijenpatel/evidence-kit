"""Content-addressed artifact storage.

The path is derived from the bytes, so identical fetches — across time or across
sources — collapse to one file, and a manifest entry's `raw_bytes_sha256` is enough
to locate the artifact without consulting an index.
"""

import hashlib
import os
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def cache_relpath(sha256_hex: str) -> str:
    """Cache-root-relative path for a digest: sha256/<first-2>/<full>.

    Sharded on the first two hex characters because a flat directory of tens of
    thousands of entries is slow to list on most filesystems. No extension: the path
    must stay stable, and an extension would encode a guess about content into it.
    """
    if not HEX64.match(sha256_hex):
        raise ValueError(
            f"not a lowercase 64-character hex digest: {sha256_hex!r}")
    return f"sha256/{sha256_hex[:2]}/{sha256_hex}"


def cache_path(cache_root: str, sha256_hex: str) -> str:
    """Absolute path of the artifact with this digest under cache_root."""
    return os.path.join(cache_root, cache_relpath(sha256_hex))


def write_artifact(cache_root: str, body: bytes) -> tuple[str, str]:
    """Store body at its content-addressed path; return (digest, relpath).

    Idempotent by construction: if the file exists its contents are already these
    bytes, so it is left untouched rather than rewritten. That keeps mtime meaningful
    as "first seen" and makes a re-run cheap.
    """
    digest = hashlib.sha256(body).hexdigest()
    rel = cache_relpath(digest)
    full = os.path.join(cache_root, rel)
    if not os.path.exists(full):
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".part"
        with open(tmp, "wb") as fh:
            fh.write(body)
        os.replace(tmp, full)        # atomic: a reader never sees a partial artifact
    return digest, rel

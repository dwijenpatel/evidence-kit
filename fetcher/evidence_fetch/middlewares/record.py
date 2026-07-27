"""Downloader middleware that writes one manifest entry per attempt.

Registered at priority 1000 — above HttpCompressionMiddleware (590) and
HttpCacheMiddleware (900) — so `process_response` sees the response first,
wire-faithful: bodies are hashed as the octets the server sent, and a
cache-served response arrives already carrying the "cached" flag.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

from evidence_fetch.backoff import classify_status
from evidence_fetch.cache import write_artifact
from evidence_fetch.manifest import (
    ManifestSchemaError,
    append_entry,
    load_prior_index,
)


def _utc_now_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds") \
        .replace("+00:00", "Z")


def _headers_dict(headers) -> dict:
    # Names arrive already Title-Cased by Scrapy (Headers.normkey = key.title(),
    # applied below every middleware); values are byte-preserved, repeats join ", ".
    return {k.decode("latin-1"): ", ".join(v.decode("latin-1") for v in vs)
            for k, vs in headers.items()}


class RecordMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler
        settings = crawler.settings
        self.cache_root = settings.get("EVIDENCE_CACHE_ROOT")
        self.manifest_path = settings.get("EVIDENCE_MANIFEST_PATH")
        if not self.cache_root or not self.manifest_path:
            raise ValueError(
                "EVIDENCE_CACHE_ROOT and EVIDENCE_MANIFEST_PATH must be set")
        self._prior = load_prior_index(self.manifest_path)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _fetch_policy(self, request) -> dict:
        downloader = self.crawler.engine.downloader
        # Response lines subscript the slot on purpose: the slot must exist here
        # (this very request refreshed lastseen), and a .get() would hide a bug.
        slot = downloader.slots[downloader.get_slot_key(request)]
        parts = urlparse(request.url)
        netloc = parts.netloc
        info = getattr(self.crawler, "robots_info", {}).get(netloc)
        if info is None:
            # The robots fetch's own entry, and any entry recorded before the
            # robots middleware stored provenance: synthesize the URL with the
            # netloc (port kept, matching how the middleware builds it) and
            # leave the two observation fields null — never a second robots GET.
            info = {"robots_url": f"{parts.scheme}://{netloc}/robots.txt",
                    "robots_sha256": None, "robots_fetched_at": None}
        return {"delay_used_s": float(slot.delay),
                "robots_url": info["robots_url"],
                "robots_sha256": info["robots_sha256"],
                "robots_fetched_at": info["robots_fetched_at"]}

    def process_response(self, request, response, spider):
        if "cached" in response.flags:
            # A cache hit is not an attempt (rule 15): no entry, no artifact.
            return response

        digest, rel = write_artifact(self.cache_root, response.body)
        redirect_chain = list(request.meta.get("redirect_urls", [])) + [request.url]
        url_requested = redirect_chain[0]
        etag_raw = response.headers.get("Etag")
        etag = etag_raw.decode("latin-1") if etag_raw is not None else None
        last_modified = response.headers.get("Last-Modified")
        content_type = response.headers.get("Content-Type")
        ua = request.headers.get("User-Agent")
        attempt_n = request.meta.get("attempt_n", 1)
        # attempt_n is 1-based; classify_status takes 0-based, converted once.
        disposition = classify_status(response.status, attempt_n - 1).value

        entry = {
            "schema": 1,
            "url_requested": url_requested,
            "url_final": request.url,
            "attempt_n": attempt_n,
            "fetched_at": _utc_now_ms(),
            "http_status": response.status,
            "response_protocol": response.protocol or None,
            "raw_bytes_sha256": digest,
            "raw_bytes_length": len(response.body),
            "cache_relpath": rel,
            "content_type": content_type.decode("latin-1") if content_type else None,
            "request_headers": _headers_dict(request.headers),
            "response_headers": _headers_dict(response.headers),
            "redirect_chain": redirect_chain,
            "etag": etag,
            "etag_is_weak": etag.startswith("W/") if etag is not None else None,
            "last_modified":
                last_modified.decode("latin-1") if last_modified else None,
            "disposition": disposition,
            "fetch_policy": self._fetch_policy(request),
            "useragent_sent": ua.decode("latin-1") if ua is not None else None,
            "prior_fetch_ref": self._prior.get(url_requested),
            "seed_signal": request.meta.get("seed_signal"),
            "failure": None,
        }
        try:
            append_entry(self.manifest_path, entry)
        except ManifestSchemaError:
            # A schema violation is a bug in this code, and continuing would
            # write unusable records. Raising alone is swallowed as this
            # request's download error (probed), so stop the engine explicitly;
            # the CLI reads this finish_reason and exits 1.
            self.crawler.engine.close_spider(spider, "manifest-schema-violation")
            raise
        if 200 <= response.status < 300:
            self._prior[url_requested] = digest
            if entry["seed_signal"] is not None:
                self.crawler.stats.inc_value("evidence_fetch/seed_2xx")
        return response

"""`python -m evidence_fetch` — the operator entry point.

Startup failures exit 2 before any network call; a completed crawl exits 0
regardless of per-URL outcomes (`blocked` is a claim about an attempt sequence,
never about the world); a manifest schema violation — a bug in this code —
stops the crawl and exits 1.
"""

import argparse
import os
import sys
from urllib.parse import urlparse

from evidence_fetch.seeds import SeedFormatError, read_seeds


def _startup_error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="evidence-fetch")
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--manifest", required=True)
    # Checked by hand, not argparse-required: the pinned message names the flag.
    parser.add_argument("--contact", default=None)
    parser.add_argument("--jobdir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    if not args.contact:
        # RFC 9309 §2.2.1: an unidentified crawler falls under the most
        # restrictive `*` robots group, and settings.USER_AGENT carries a
        # literal {contact} placeholder that must never reach the wire.
        return _startup_error("--contact is required")

    if not os.path.isfile(args.seeds):
        return _startup_error(f"no such seeds file: {args.seeds}")
    try:
        seeds = read_seeds(args.seeds)
    except SeedFormatError as exc:
        return _startup_error(str(exc))

    # Validate every seed URL before the crawler exists: a bad URL raised
    # inside `async def start()` kills the generator and silently drops every
    # later seed while the run exits 0 (probed) — never start a partial crawl
    # from a malformed queue.
    for seed in seeds:
        parts = urlparse(seed.url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return _startup_error(f"seed url is not fetchable: {seed.url!r}")

    cache_root = args.cache_root
    try:
        os.makedirs(cache_root, exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(args.manifest)),
                    exist_ok=True)
        probe = os.path.join(cache_root, ".write-probe")
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
    except OSError as exc:
        return _startup_error(f"cache root is not writable: {exc}")

    if not seeds:
        return 0    # a guard-valid empty table is a no-op, not an error

    # Imports deferred so the startup failures above never pay reactor cost.
    from scrapy.crawler import CrawlerProcess
    from scrapy.settings import Settings

    from evidence_fetch import settings as base_settings
    from evidence_fetch.spiders.fetch import FetchSpider

    settings = Settings()
    settings.setmodule(base_settings)
    settings.set("EVIDENCE_CACHE_ROOT", cache_root)
    settings.set("EVIDENCE_MANIFEST_PATH", args.manifest)
    settings.set("USER_AGENT",
                 base_settings.USER_AGENT.format(contact=args.contact))
    # Both land under the cache root so the single `cache/` ignore line covers
    # everything the fetcher writes; data_path() passes absolute paths through,
    # while the bare "httpcache" default would land in <cwd>/.scrapy/.
    settings.set("HTTPCACHE_DIR",
                 os.path.join(os.path.abspath(cache_root), "httpcache"))
    settings.set("JOBDIR",
                 args.jobdir or os.path.join(cache_root, ".jobdir"))

    process = CrawlerProcess(settings)
    crawler = process.create_crawler(FetchSpider)
    process.crawl(crawler, seeds_path=args.seeds, limit=args.limit)
    process.start()

    if crawler.stats.get_value("finish_reason") == "manifest-schema-violation":
        print("error: crawl stopped on manifest-schema-violation",
              file=sys.stderr)
        return 1
    return 0

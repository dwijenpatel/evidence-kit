"""Subprocess driver for the end-to-end tests: run one crawl, in-process.

Not a test module (discovery matches test*.py). Usage:
    python _crawl.py <seeds.md> <cache-root> <manifest.jsonl>

Mirrors what the CLI will derive at runtime (HTTPCACHE_DIR under the cache
root); overrides DOWNLOAD_DELAY and USER_AGENT for test speed and a concrete
contact — politeness values themselves are asserted by test_settings.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapy.crawler import CrawlerProcess  # noqa: E402
from scrapy.settings import Settings  # noqa: E402

from evidence_fetch import settings as base_settings  # noqa: E402
from evidence_fetch.spiders.fetch import FetchSpider  # noqa: E402


def main() -> None:
    seeds_path, cache_root, manifest_path = sys.argv[1:4]
    os.makedirs(cache_root, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)

    settings = Settings()
    settings.setmodule(base_settings)
    settings.set("EVIDENCE_CACHE_ROOT", cache_root)
    settings.set("EVIDENCE_MANIFEST_PATH", manifest_path)
    settings.set("HTTPCACHE_DIR",
                 os.path.join(os.path.abspath(cache_root), "httpcache"))
    settings.set("DOWNLOAD_DELAY", 0)
    settings.set("USER_AGENT", "evidence-fetch/0.1 (+mailto:ops@example.invalid)")

    process = CrawlerProcess(settings, install_root_handler=False)
    process.crawl(FetchSpider, seeds_path=seeds_path)
    process.start()


if __name__ == "__main__":
    main()

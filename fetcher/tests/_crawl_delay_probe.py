"""Subprocess driver for the real-traffic crawl-delay tests.

Runs a crawl with a probe spider that prints the live slot delay from inside
the callback (where crawler.engine is real). Usage:
    python _crawl_delay_probe.py <seeds.md> <cache-root> <manifest.jsonl> <download-delay>

Emits one `SLOTDELAY <value>` line per response to stdout.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapy.crawler import CrawlerProcess  # noqa: E402
from scrapy.settings import Settings  # noqa: E402

from evidence_fetch import settings as base_settings  # noqa: E402
from evidence_fetch.spiders.fetch import FetchSpider  # noqa: E402


class ProbeSpider(FetchSpider):
    name = "probe"

    def parse(self, response):
        downloader = self.crawler.engine.downloader
        key = downloader.get_slot_key(response.request)
        print(f"SLOTDELAY {downloader.slots[key].delay}", flush=True)


def main() -> None:
    seeds_path, cache_root, manifest_path, download_delay = sys.argv[1:5]
    os.makedirs(cache_root, exist_ok=True)

    settings = Settings()
    settings.setmodule(base_settings)
    settings.set("EVIDENCE_CACHE_ROOT", cache_root)
    settings.set("EVIDENCE_MANIFEST_PATH", manifest_path)
    settings.set("HTTPCACHE_DIR",
                 os.path.join(os.path.abspath(cache_root), "httpcache"))
    settings.set("DOWNLOAD_DELAY", float(download_delay))
    settings.set("USER_AGENT", "evidence-fetch/0.1 (+mailto:ops@example.invalid)")

    process = CrawlerProcess(settings, install_root_handler=False)
    process.crawl(ProbeSpider, seeds_path=seeds_path)
    process.start()


if __name__ == "__main__":
    main()

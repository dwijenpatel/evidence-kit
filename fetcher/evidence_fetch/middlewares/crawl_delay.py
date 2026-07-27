"""RobotsTxtMiddleware that also enforces the Crawl-delay it parses.

Scrapy parses Crawl-delay through Protego and then discards it — the defect
that produced this project's founding incident. This subclass reads the
declared delay when a host's parser resolves and writes it to that host's
downloader slot, and it records robots.txt provenance (URL, body digest,
timestamp) on the crawler for the record middleware — the only moment the
robots bytes are observable before Scrapy keeps just the parser.
"""

import hashlib
import logging
from datetime import datetime, timezone

from scrapy.downloadermiddlewares.robotstxt import RobotsTxtMiddleware
from scrapy.utils.httpobj import urlparse_cached

logger = logging.getLogger(__name__)


def _utc_now_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds") \
        .replace("+00:00", "Z")


class CrawlDelayRobotsMiddleware(RobotsTxtMiddleware):
    def __init__(self, crawler):
        super().__init__(crawler)
        self.crawler = crawler
        self.DEFAULT_DELAY = crawler.settings.getfloat("DOWNLOAD_DELAY", 5.0)
        self.MAX_DELAY = crawler.settings.getfloat("CRAWL_DELAY_CEILING", 60.0)
        self._applied: set[str] = set()      # netlocs whose delay is now set
        # netloc -> first scheme seen. Must live here, not lazily in the 6a
        # methods: on the _robots_error-first path a lazy init would be
        # swallowed silently, and in robot_parser it would raise outside the
        # superclass try and kill every request.
        self._scheme_by_netloc: dict[str, str] = {}
        crawler.robots_info = {}             # netloc -> robots provenance

    async def process_request(self, request, spider=None):
        if request.meta.get("dont_obey_robotstxt"):
            return
        if request.url.startswith(("data:", "file:")):
            return
        parser = await self.robot_parser(request)
        if parser is not None:
            self._apply_delay(request, parser)
        self.process_request_2(parser, request)

    async def robot_parser(self, request):
        url = urlparse_cached(request)
        # First scheme wins, matching Scrapy's own one-parser-per-netloc
        # keying — its _parsers dict is scheme-less.
        self._scheme_by_netloc.setdefault(url.netloc, url.scheme)
        return await super().robot_parser(request)

    def _parse_robots(self, response, netloc):
        # A delivered robots response is always recorded with its digest and
        # timestamp, whatever its status — the digest of whatever bytes the
        # host served IS the fidelity record. Recorded before the body is
        # handed to the parser and lost.
        self.crawler.robots_info[netloc] = {
            "robots_url": response.url,
            "robots_sha256": hashlib.sha256(response.body).hexdigest(),
            "robots_fetched_at": _utc_now_ms(),
        }
        return super()._parse_robots(response, netloc)

    def _robots_error(self, exc, netloc):
        # No response existed at all: record "we asked" with nulls. The scheme
        # is stashed by robot_parser — this hook receives none, and a
        # hardcoded http:// would name a different origin on every https host.
        scheme = self._scheme_by_netloc.get(netloc, "http")
        self.crawler.robots_info[netloc] = {
            "robots_url": f"{scheme}://{netloc}/robots.txt",
            "robots_sha256": None, "robots_fetched_at": None}
        return super()._robots_error(exc, netloc)

    def _apply_delay(self, request, parser):
        downloader = self.crawler.engine.downloader
        netloc = urlparse_cached(request).netloc  # the MEMO key: host:port
        if netloc in self._applied:
            return
        key = downloader.get_slot_key(request)   # the slot LOOKUP key:
                                                 # hostname, port stripped —
                                                 # never the netloc
        # Look the slot up FIRST. Marking a netloc applied before we have a
        # slot strands it forever: the guard above returns on every later call
        # and the declared delay is never applied.
        slot = downloader.slots.get(key)
        if slot is None:
            return                            # not marked; retried next request
        try:
            # .rp, not the wrapper: Scrapy hands ProtegoRobotParser around,
            # and only its .rp (the Protego instance) has crawl_delay.
            declared = parser.rp.crawl_delay(self._robotstxt_useragent
                                             or self.crawler.settings["USER_AGENT"])
        except Exception:
            logger.warning("crawl_delay lookup failed for %s; using DEFAULT_DELAY",
                           netloc)
            declared = None
        self._applied.add(netloc)             # a slot existed: origin settled
        if declared is None:
            return                            # keep DOWNLOAD_DELAY; never zero
        slot.delay = max(slot.delay, min(float(declared), self.MAX_DELAY))

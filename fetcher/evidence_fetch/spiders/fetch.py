"""The fetch spider: seeds in, requests out.

The spider's whole job is scheduling. Caching and recording live in the record
middleware; the callback never touches the body.
"""

import asyncio
from datetime import datetime, timezone

import scrapy

from evidence_fetch.backoff import (Disposition, backoff_delay, classify_status,
                                    parse_retry_after)
from evidence_fetch.seeds import read_seeds


class FetchSpider(scrapy.Spider):
    name = "fetch"
    # Without this, HttpErrorMiddleware drops every non-2xx before the callback —
    # the recorder still writes the line, but retry decisions would never fire.
    custom_settings = {"HTTPERROR_ALLOW_ALL": True}

    def __init__(self, seeds_path, limit=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seeds_path = seeds_path
        self.limit = int(limit) if limit is not None else None

    def _limit_reached(self) -> bool:
        # The recorder counts 2xx responses with a non-null seed_signal;
        # robots fetches are overhead, not yield, and never advance it.
        if self.limit is None:
            return False
        recorded = self.crawler.stats.get_value("evidence_fetch/seed_2xx", 0)
        return recorded >= self.limit

    async def start(self):
        # scrapy 2.17: the classic start_requests() is consulted by nothing.
        seen: set[str] = set()
        for seed in read_seeds(self.seeds_path):
            if seed.url in seen:
                self.logger.warning("duplicate seed (row ignored): %s", seed.url)
                continue
            seen.add(seed.url)
            if self._limit_reached():
                return
            yield scrapy.Request(
                seed.url,
                callback=self.parse,
                meta={"attempt_n": 1, "seed_signal": seed.signal},
                dont_filter=False,
            )

    async def parse(self, response):
        # Recording happened in the middleware; the callback's whole job is the
        # retry decision. The spider is the ONLY retry mechanism: Scrapy's
        # RetryMiddleware is off because it cannot honour Retry-After.
        n = response.request.meta.get("attempt_n", 1)
        zero_based = n - 1      # computed once, passed to both functions
        if classify_status(response.status, zero_based) is not Disposition.RETRY:
            return
        header = response.headers.get("Retry-After")
        ra = parse_retry_after(
            header.decode("latin-1") if header is not None else None,
            datetime.now(timezone.utc))
        # `is not None`, never `or`: an honoured "retry now" is 0.0, and
        # `0.0 or x` would silently replace it with a random backoff.
        delay_s = ra if ra is not None else backoff_delay(zero_based)
        # Genuinely defer before handing the retry to the scheduler; an
        # immediate re-yield hides behind the slot delay but breaks Retry-After.
        await asyncio.sleep(delay_s)
        # dont_filter=True: the dupefilter has already seen this fingerprint,
        # and without the flag every retry is eaten silently. Seeds keep False.
        yield response.request.replace(
            dont_filter=True,
            meta={**response.request.meta, "attempt_n": n + 1})

"""The fetch spider: seeds in, requests out.

The spider's whole job is scheduling. Caching and recording live in the record
middleware; the callback never touches the body.
"""

import scrapy

from evidence_fetch.seeds import read_seeds


class FetchSpider(scrapy.Spider):
    name = "fetch"
    # Without this, HttpErrorMiddleware drops every non-2xx before the callback —
    # the recorder still writes the line, but retry decisions would never fire.
    custom_settings = {"HTTPERROR_ALLOW_ALL": True}

    def __init__(self, seeds_path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seeds_path = seeds_path

    async def start(self):
        # scrapy 2.17: the classic start_requests() is consulted by nothing.
        for seed in read_seeds(self.seeds_path):
            yield scrapy.Request(
                seed.url,
                callback=self.parse,
                meta={"attempt_n": 1, "seed_signal": seed.signal},
                dont_filter=False,
            )

    def parse(self, response):
        # Recording happened in the middleware; retry decisions land with the
        # backoff work. Nothing to do on the happy path.
        return

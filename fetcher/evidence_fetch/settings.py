"""Scrapy settings: politeness first, storage second.

Every value here is a PRD or CLAUDE.md constraint, not a tuning preference. The
`Crawl-delay` enforcement these settings cannot express lives in the middleware added
by task 3 — Scrapy parses Crawl-delay via Protego and discards it.
"""

BOT_NAME = "evidence-fetch"
SPIDER_MODULES = ["evidence_fetch.spiders"]
NEWSPIDER_MODULE = "evidence_fetch.spiders"

# --- politeness (CLAUDE.md rule 17) -----------------------------------------
ROBOTSTXT_OBEY = True
# One connection per host, always. The comment sits ABOVE the assignment on purpose:
# the gating check anchors the whole line (`^CONCURRENT_REQUESTS_PER_DOMAIN = 1$`),
# and a trailing comment turns that check red against this task's own code (R7).
CONCURRENT_REQUESTS_PER_DOMAIN = 1
CONCURRENT_REQUESTS = 8                 # across hosts; politeness is per-host
DOWNLOAD_DELAY = 5.0                    # floor where no Crawl-delay is declared

# A1 requires "waits >= the declared Crawl-delay". Both of the following would
# break that, and both were measured breaking it — see plan.md Amendment 1.
#
#   AUTOTHROTTLE_ENABLED = True   ->  AutoThrottle's _adjust_delay runs on every
#       response and ends `slot.delay = new_delay`, clamped to a GLOBAL floor of
#       DOWNLOAD_DELAY. A per-host 7.0 is dragged back to 5.0 by the FIRST 200.
#       There is no per-host mindelay, so no configuration rescues this.
#   RANDOMIZE_DOWNLOAD_DELAY = True  ->  Slot.download_delay() returns
#       uniform(0.5*delay, 1.5*delay); at delay=7.0 the floor is 3.5s.
#       A declared delay is a MINIMUM, and jitter below a minimum is a violation.
AUTOTHROTTLE_ENABLED = False
RANDOMIZE_DOWNLOAD_DELAY = False

# The rule-17 ceiling. Deliberately NOT AUTOTHROTTLE_MAX_DELAY: that setting is
# inert once AutoThrottle is off, and reading an inert setting is a trap for the
# next person who turns AutoThrottle back on. Task 3 reads this name.
CRAWL_DELAY_CEILING = 60.0

# A dead host must not hold an unattended run for a quarter of an hour. Scrapy's
# default is 180s (probed, 2.17.0): the robots fetch plus four page attempts is
# ~15 minutes per hung host, and each backoff wait sits in the callback frame
# (T14), so the window in which a forced stop strands a retry scales with it.
# 30.0 is the value task 5's timeout sample was written against ("took longer
# than 30.0 seconds" is scrapy's own message at this setting). Operator-decided
# (round-4 U2). Comment above the line: the check anchors it whole (R7).
DOWNLOAD_TIMEOUT = 30.0

# Identify the crawler. RFC 9309 §2.2.1: robots.txt groups match on a product token,
# so an unidentified crawler falls under the most restrictive `*` group.
USER_AGENT = "evidence-fetch/0.1 (+{contact})"

# --- storage ----------------------------------------------------------------
# DummyPolicy serves every STORED response regardless of HTTP cache semantics, which
# is what "resume without refetching what I already have" means here (A9). This is a
# fetch-avoidance layer only; the durable artifact is the content-addressed file the
# manifest points at, so HTTPCACHE_DIR may be deleted at any time without data loss.
HTTPCACHE_ENABLED = True
HTTPCACHE_POLICY = "scrapy.extensions.httpcache.DummyPolicy"
HTTPCACHE_EXPIRATION_SECS = 0           # 0 = never expire
# What gets STORED is filtered: DummyPolicy.should_cache_response consults this list
# (probed, 2.17.0). Retryable statuses must never be stored -- DummyPolicy serves a
# stored 403 to every later request for that URL, so the spider's retries (task 6
# item 7) would be answered from disk, flagged "cached", skipped by the recorder,
# and backoff would never touch the wire (plan-review R4; probed: 4 callbacks, ONE
# wire hit). The list must equal backoff.RETRYABLE (task 4); a test there asserts
# the equality, because this module is built before backoff.py exists and must not
# import it. The comment sits above the line for the same R7 reason as above.
HTTPCACHE_IGNORE_HTTP_CODES = [403, 408, 429, 500, 502, 503, 504, 522, 524]
# A RELATIVE value here resolves through scrapy.utils.project.data_path to
# <cwd>/.scrapy/httpcache -- outside the cache root and outside the one
# `cache/` ignore line. The CLI (task 6) overrides this at runtime to
# <abspath(cache-root)>/httpcache; data_path passes absolute paths through
# unchanged. This default is a fallback, never the operating value. (#15)
HTTPCACHE_DIR = "httpcache"

# --- recording --------------------------------------------------------------
# The recorder must see the response first, wire-faithful: 1000 sits above
# HttpCompressionMiddleware (590) and HttpCacheMiddleware (900), so bodies are
# hashed as wire octets and cache-served responses arrive already flagged.
DOWNLOADER_MIDDLEWARES = {
    # The stock robots middleware must be OFF, not merely outranked: with both
    # registered, robots.txt is fetched twice per host and the stock one may
    # short-circuit first.
    "scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware": None,
    "evidence_fetch.middlewares.crawl_delay.CrawlDelayRobotsMiddleware": 100,
    "evidence_fetch.middlewares.record.RecordMiddleware": 1000,
}

# --- retry ------------------------------------------------------------------
# The SPIDER is the only retry mechanism (task 6 item 7): classify_status decides,
# backoff_delay/parse_retry_after pace. Scrapy's RetryMiddleware must stay off --
# its source contains zero occurrences of "Retry-After", so with it on, a 503
# carrying `Retry-After: 120` is retried at the slot delay and the header is never
# honoured; worse, the callback never sees a retryable response while its retries
# remain, so the spider's own retry logic becomes dead code. (Plan-review F5.)
RETRY_ENABLED = False

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# Deliberately absent — both are `scrapy startproject` template leftovers, and neither
# is a PRD or CLAUDE.md constraint (the docstring above says every value here is one):
#   REQUEST_FINGERPRINTER_IMPLEMENTATION — removed from scrapy; 2.17.0 contains ZERO
#     occurrences of the name, reads it nowhere, warns never (probed). Only
#     REQUEST_FINGERPRINTER_CLASS exists, and its default is correct.
#   FEED_EXPORT_ENCODING — a real setting, but consumed only by feed exports, and
#     CLAUDE.md rule 14 forbids this component a third write path.

import unittest

from evidence_fetch import settings


class PolitenessSettingsTests(unittest.TestCase):
    def test_politeness_settings_hold(self):
        self.assertEqual(settings.CONCURRENT_REQUESTS_PER_DOMAIN, 1)
        self.assertTrue(settings.ROBOTSTXT_OBEY)
        self.assertGreaterEqual(settings.DOWNLOAD_DELAY, 5.0)
        self.assertEqual(settings.CRAWL_DELAY_CEILING, 60.0)
        # Scrapy's default is 180 -- a hung host would hold an unattended run
        # ~15 minutes (round-4 U2, operator-decided).
        self.assertEqual(settings.DOWNLOAD_TIMEOUT, 30.0)

    def test_settings_that_defeat_a1_stay_off(self):
        # AutoThrottle rewrites slot.delay with a global DOWNLOAD_DELAY floor;
        # randomize jitters below a declared minimum. Both measured breaking A1.
        self.assertFalse(settings.AUTOTHROTTLE_ENABLED)
        self.assertFalse(settings.RANDOMIZE_DOWNLOAD_DELAY)

    def test_scrapy_retry_stays_off(self):
        # The spider owns retry so Retry-After is honoured (plan-review F5).
        self.assertFalse(settings.RETRY_ENABLED)
        self.assertFalse(hasattr(settings, "RETRY_HTTP_CODES"))

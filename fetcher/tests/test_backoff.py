import unittest
from datetime import datetime, timezone

from evidence_fetch.backoff import (RETRYABLE, Disposition, backoff_delay,
                                    classify_failure, classify_status,
                                    failure_class_for, parse_retry_after)

NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)


class RetryAfterTests(unittest.TestCase):
    def test_seconds_form(self):
        self.assertEqual(parse_retry_after("120", NOW), 120.0)

    def test_http_date_form(self):
        self.assertEqual(
            parse_retry_after("Sat, 25 Jul 2026 12:02:00 GMT", NOW), 120.0)

    def test_past_date_clamps_to_zero(self):
        self.assertEqual(
            parse_retry_after("Sat, 25 Jul 2026 11:58:00 GMT", NOW), 0.0)

    def test_negative_seconds_clamp_to_zero(self):
        self.assertEqual(parse_retry_after("-5", NOW), 0.0)

    def test_absent_and_garbage_are_none(self):
        self.assertIsNone(parse_retry_after(None, NOW))
        self.assertIsNone(parse_retry_after("soon", NOW))


class BackoffTests(unittest.TestCase):
    def test_full_jitter_upper_bound_doubles(self):
        hi = lambda: 1.0
        self.assertEqual([backoff_delay(a, rand=hi) for a in range(4)],
                         [1.0, 2.0, 4.0, 8.0])

    def test_capped(self):
        self.assertEqual(backoff_delay(6, rand=lambda: 1.0), 60.0)

    def test_lower_bound_is_zero(self):
        self.assertEqual(backoff_delay(3, rand=lambda: 0.0), 0.0)

    def test_negative_attempt_rejected(self):
        with self.assertRaises(ValueError):
            backoff_delay(-1)


class ClassifyTests(unittest.TestCase):
    def test_403_is_retryable_before_exhaustion(self):
        self.assertIs(classify_status(403, attempt=0), Disposition.RETRY)

    def test_403_becomes_blocked_only_after_exhaustion(self):
        self.assertIs(classify_status(403, attempt=3), Disposition.BLOCKED)

    def test_429_and_503_are_retryable(self):
        for s in (429, 503):
            self.assertIs(classify_status(s, attempt=0), Disposition.RETRY)

    def test_404_is_fatal_immediately(self):
        self.assertIs(classify_status(404, attempt=0), Disposition.FATAL)

    def test_success_is_ok(self):
        self.assertIs(classify_status(200, attempt=0), Disposition.OK)


class FailureClassTests(unittest.TestCase):
    def test_probed_scrapy_names_map(self):
        self.assertEqual(failure_class_for("CannotResolveHostError"), "dns-failure")
        self.assertEqual(failure_class_for("DownloadConnectionRefusedError"),
                         "connection-refused")
        self.assertEqual(failure_class_for("DownloadTimeoutError"), "timeout")

    def test_tls_needs_ssl_in_the_detail(self):
        self.assertEqual(
            failure_class_for("DownloadFailedError",
                              "[<twisted.python.failure.Failure OpenSSL.SSL.Error"),
            "tls-error")
        self.assertEqual(failure_class_for("DownloadFailedError", "who knows"),
                         "other")

    def test_robots_disallow_is_ignore_request_plus_robots(self):
        self.assertEqual(
            failure_class_for("IgnoreRequest", "Forbidden by robots.txt"),
            "robots-disallowed")
        self.assertEqual(failure_class_for("IgnoreRequest", "other reason"), "other")

    def test_unknown_exception_is_other(self):
        self.assertEqual(failure_class_for("SomethingNovel"), "other")


class ClassifyFailureTests(unittest.TestCase):
    def test_robots_disallowed_blocks_immediately(self):
        self.assertIs(classify_failure("robots-disallowed", attempt=0),
                      Disposition.BLOCKED)

    def test_transport_failures_retry_then_block(self):
        for fc in ("dns-failure", "connection-refused", "timeout", "tls-error",
                   "other"):
            self.assertIs(classify_failure(fc, attempt=0), Disposition.RETRY, fc)
            self.assertIs(classify_failure(fc, attempt=3), Disposition.BLOCKED, fc)


class CacheRetrySeamTests(unittest.TestCase):
    def test_httpcache_ignores_exactly_the_retryable_set(self):
        # Task 2's HTTPCACHE_IGNORE_HTTP_CODES keeps retryable responses OUT of
        # Scrapy's cache. DummyPolicy serves a stored 403 to every later request
        # for that URL, so a drifted list means retries are answered from disk and
        # backoff never touches the wire (plan-review R4). settings.py is built
        # before this module exists and must not import it, so this equality test
        # is the seam's only guard.
        from evidence_fetch import settings
        self.assertEqual(set(settings.HTTPCACHE_IGNORE_HTTP_CODES), RETRYABLE)

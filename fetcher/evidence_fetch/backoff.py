"""Status/failure taxonomy and retry pacing.

This module currently holds only the failure-class taxonomy, which the manifest
validator needs; classification and pacing (`classify_status`, `backoff_delay`,
`parse_retry_after`, `RETRYABLE`) land with the retry work.
"""

FAILURE_CLASSES = ("dns-failure", "connection-refused", "timeout", "tls-error",
                   "robots-disallowed", "other")

import gzip
import io
import time
import unittest
import urllib.error

from aptrack import fetch


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    """Stands in for urlopen: plays back a list of bodies (bytes) or HTTP status codes (int)."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0
        self.requests = []

    def __call__(self, request, timeout=None):
        self.calls += 1
        self.requests.append(request)
        step = self.script.pop(0)
        if isinstance(step, int):
            raise urllib.error.HTTPError(request.full_url, step, "error", {}, io.BytesIO(b""))
        return Response(step)


def no_sleep(seconds):
    pass


class GetTests(unittest.TestCase):
    def test_gzip_body_is_decompressed(self):
        op = Opener(gzip.compress(b'{"a":1}'))
        self.assertEqual(fetch.get("https://x.test/a", opener=op), b'{"a":1}')

    def test_plain_body_is_returned_as_is(self):
        op = Opener(b"plain")
        self.assertEqual(fetch.get("https://x.test/a", opener=op), b"plain")

    def test_sends_browser_user_agent(self):
        op = Opener(b"ok")
        fetch.get("https://x.test/a", opener=op)
        self.assertIn("Mozilla", op.requests[0].get_header("User-agent"))

    def test_extra_headers_replace_the_defaults(self):
        op = Opener(b"ok")
        fetch.get("https://x.test/a", opener=op, headers={"User-Agent": "aptrack/0.1"})
        self.assertEqual(op.requests[0].get_header("User-agent"), "aptrack/0.1")

    def test_404_raises_gone(self):
        op = Opener(404)
        with self.assertRaises(fetch.Gone):
            fetch.get("https://x.test/a", opener=op, sleep=no_sleep)
        self.assertEqual(op.calls, 1)

    def test_429_raises_rate_limited_without_retry(self):
        op = Opener(429, b"never reached")
        with self.assertRaises(fetch.RateLimited):
            fetch.get("https://x.test/a", opener=op, sleep=no_sleep)
        self.assertEqual(op.calls, 1)

    def test_500_is_retried_then_succeeds(self):
        op = Opener(500, 502, b"ok")
        self.assertEqual(fetch.get("https://x.test/a", opener=op, sleep=no_sleep), b"ok")
        self.assertEqual(op.calls, 3)

    def test_gives_up_after_tries_and_raises_last_error(self):
        op = Opener(500, 500, 503)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            fetch.get("https://x.test/a", opener=op, sleep=no_sleep)
        self.assertEqual(caught.exception.code, 503)
        self.assertEqual(op.calls, 3)


class ThrottleTests(unittest.TestCase):
    def test_throttle_spaces_same_host(self):
        throttle = fetch.Throttle(0.2)
        start = time.monotonic()
        throttle.wait("https://a.test/1")
        throttle.wait("https://a.test/2")
        self.assertGreaterEqual(time.monotonic() - start, 0.2)

    def test_throttle_does_not_delay_other_hosts(self):
        throttle = fetch.Throttle(0.5)
        start = time.monotonic()
        throttle.wait("https://a.test/1")
        throttle.wait("https://b.test/1")
        self.assertLess(time.monotonic() - start, 0.4)


class SiteDelayTests(unittest.TestCase):
    def test_a_site_can_have_its_own_shorter_delay(self):
        throttle = fetch.Throttle(0.5, delays={"fast.test": 0.0})
        start = time.monotonic()
        throttle.wait("https://fast.test/1")
        throttle.wait("https://fast.test/2")
        throttle.wait("https://fast.test/3")
        self.assertLess(time.monotonic() - start, 0.3)

    def test_a_site_can_have_its_own_longer_delay(self):
        throttle = fetch.Throttle(0.0, delays={"slow.test": 0.2})
        start = time.monotonic()
        throttle.wait("https://slow.test/1")
        throttle.wait("https://slow.test/2")
        self.assertGreaterEqual(time.monotonic() - start, 0.2)

    def test_polite_get_takes_site_delays(self):
        op = Opener(b"one", b"two")
        get = fetch.polite(0.0, delays={"a.test": 0.2}, opener=op)
        start = time.monotonic()
        get("https://a.test/1")
        get("https://a.test/2")
        self.assertGreaterEqual(time.monotonic() - start, 0.2)


class PoliteTests(unittest.TestCase):
    def test_polite_get_fetches_and_spaces_requests_to_one_host(self):
        op = Opener(b"one", b"two")
        get = fetch.polite(0.2, opener=op)
        start = time.monotonic()
        self.assertEqual((get("https://a.test/1"), get("https://a.test/2")), (b"one", b"two"))
        self.assertGreaterEqual(time.monotonic() - start, 0.2)

    def test_polite_get_passes_headers_through(self):
        op = Opener(b"ok")
        fetch.polite(0, opener=op)("https://a.test/1", headers={"User-Agent": "aptrack/0.1"})
        self.assertEqual(op.requests[0].get_header("User-agent"), "aptrack/0.1")


if __name__ == "__main__":
    unittest.main()

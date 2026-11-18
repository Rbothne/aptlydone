"""Polite HTTP: one request at a time per site, gzip, and clear errors for "gone" and "slow down"."""

import gzip
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")


class Gone(Exception):
    """The address answered 404 or 410."""


class RateLimited(Exception):
    """The site answered 429. Callers come back later instead of retrying."""


def get(url, *, timeout=25, tries=3, headers=None, opener=urllib.request.urlopen, sleep=time.sleep):
    """Fetch `url` and return the body as bytes, decompressed if the server gzipped it."""
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        **(headers or {}),
    })
    for attempt in range(tries):
        try:
            with opener(request, timeout=timeout) as response:
                body = response.read()
            return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
        except urllib.error.HTTPError as error:
            error.close()
            if error.code in (404, 410):
                raise Gone(url) from error
            if error.code == 429:
                raise RateLimited(url) from error
            last = error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last = error
        if attempt < tries - 1:
            sleep(2 * (attempt + 1))
    raise last


class Throttle:
    """Keeps requests to the same host at least `delay` seconds apart, across threads.
    `delays` gives particular hosts their own spacing: shorter for a site known to cope, longer for a touchy one."""

    def __init__(self, delay=1.0, delays=None):
        self.delay = delay
        self.delays = delays or {}
        self._next = {}
        self._lock = threading.Lock()

    def slow_down(self, host):
        """Put a site that has pushed back on the default spacing for the rest of the run (never faster than it was)."""
        with self._lock:
            self.delays[host] = max(self.delays.get(host, self.delay), self.delay)

    def wait(self, url):
        host = urlparse(url).netloc
        with self._lock:
            now = time.monotonic()
            at = max(now, self._next.get(host, now))
            self._next[host] = at + self.delays.get(host, self.delay)
        if at > now:
            time.sleep(at - now)


def polite(delay=1.0, delays=None, **defaults):
    """A `get(url, **options)` that waits its turn for each host before fetching."""
    throttle = Throttle(delay, delays)

    def polite_get(url, **options):
        throttle.wait(url)
        return get(url, **{**defaults, **options})
    polite_get.throttle = throttle
    return polite_get

"""Polite HTTP: one request at a time per site, gzip, and clear errors for "gone" and "slow down".

With exits (`aptrack/vpn.py`), a site that refuses one address is asked through the next, and the exit it answered
through is remembered for it (`Routes`).
"""

import datetime
import gzip
import json
import os
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


def get(url, *, timeout=25, tries=3, headers=None, opener=None, sleep=time.sleep, raw=False, data=None, proxy=None):
    """Fetch `url` and return the body as bytes, decompressed if the server gzipped it.
    `raw` returns the bytes exactly as sent, for a piece of a binary file that might only look gzipped.
    `data` (bytes) sends it as a POST: a listing service that answers questions (GraphQL) rather than pages.
    `proxy` (an http:// address) sends it out through that exit. A refusal (403) is not asked again here."""
    if opener is None:
        opener = (urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy})).open
                  if proxy else urllib.request.urlopen)
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET", headers={
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        **(headers or {}),
    })
    for attempt in range(tries):
        try:
            with opener(request, timeout=timeout) as response:
                body = response.read()
            return gzip.decompress(body) if body[:2] == b"\x1f\x8b" and not raw else body
        except urllib.error.HTTPError as error:
            error.close()
            if error.code in (404, 410):
                raise Gone(url) from error
            if error.code == 429:
                raise RateLimited(url) from error
            if error.code == 403:                  # asking the same address again only deepens a refusal
                raise
            last = error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last = error
        if attempt < tries - 1:
            sleep(2 * (attempt + 1))
    raise last


def post(url, body, headers=None, *, timeout=120, opener=urllib.request.urlopen):
    """Send `body` (bytes) to `url` and return the answer. No retries: the callers decide what a failure means."""
    request = urllib.request.Request(url, data=body, method="POST", headers={"User-Agent": USER_AGENT, **(headers or {})})
    with opener(request, timeout=timeout) as response:
        return response.read()


class Throttle:
    """Keeps requests to the same host at least `delay` seconds apart, across threads.
    `delays` gives particular hosts their own spacing: shorter for a site known to cope, longer for a touchy one."""

    def __init__(self, delay=1.0, delays=None):
        self.delay = delay
        self.delays = delays or {}
        self._next = {}
        self._clock = {}                      # host -> the name of a clock it shares with other hosts
        self._lock = threading.Lock()

    def share(self, hosts, name):
        """Put several hosts on one clock, `name`, spaced by `delays[name]`: sites that sit behind one service
        (many buildings' RentCafe sites, say) then take turns instead of all being asked in the same second."""
        with self._lock:
            for host in hosts:
                self._clock[host] = name

    def slow_down(self, host):
        """Put a site that has pushed back on the default spacing for the rest of the run (never faster than it was)."""
        with self._lock:
            host = self._clock.get(host, host)
            self.delays[host] = max(self.delays.get(host, self.delay), self.delay)

    def wait(self, url, lane=""):
        """`lane` is the exit the request goes out through: each exit keeps its own pace with each site."""
        host = urlparse(url).netloc
        with self._lock:
            host = self._clock.get(host, host)
            key = (lane, host)
            now = time.monotonic()
            at = max(now, self._next.get(key, now))
            self._next[key] = at + self.delays.get(host, self.delay)
        if at > now:
            time.sleep(at - now)


def refused(error, through_tunnel=False):
    """Would another exit be worth trying? A refusal of the address (403, 451, 503, 429) is; so is a tunnel that
    did not carry the request. A page that is gone (404) is gone from everywhere."""
    if isinstance(error, RateLimited):
        return True
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (403, 451, 503)
    return through_tunnel and isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


class Routes:
    """Which exit each site answers through. Learned when a site refuses one exit and answers another, and kept
    between runs in `path` (data/routes.json), separately for each place a run starts from ("github" or "local"):
    GitHub's address is refused where this machine's is not."""

    def __init__(self, exits, path=None, where=None, today=None):
        self.exits = list(exits)
        self.path = path
        self.where = where or ("github" if os.environ.get("GITHUB_ACTIONS") == "true" else "local")
        self.today = today or datetime.date.today().isoformat()
        self._lock = threading.Lock()
        try:
            with open(path, encoding="utf-8") as f:
                self.known = json.load(f)
        except (TypeError, OSError, ValueError):
            self.known = {}

    def mine(self):
        return self.known.setdefault(self.where, {})

    def order(self, host):
        """The exits to try for `host`: the one it answered through last, then the others in their usual order."""
        learned = (self.mine().get(host) or {}).get("exit")
        return sorted(self.exits, key=lambda e: e.name != learned)

    def worked(self, host, exit_):
        with self._lock:
            mine = self.mine()
            had = mine.get(host)
            if exit_.name == "direct":                     # the usual way: nothing to remember
                if had is not None:
                    del mine[host]
                    self._save()
                return
            if had and had.get("exit") == exit_.name and had.get("at") == self.today:
                return
            mine[host] = {"exit": exit_.name, "at": self.today}
            self._save()

    def _save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.known, f, indent=1, sort_keys=True)
        os.replace(self.path + ".tmp", self.path)


def polite(delay=1.0, delays=None, routes=None, **defaults):
    """A `get(url, **options)` that waits its turn for each host before fetching. With `routes`, a site that
    refuses one exit is asked through the next (once each, at that exit's own pace), and the exit that answered
    is the first one tried for that site from then on. When every exit refuses, the first refusal is raised."""
    throttle = Throttle(delay, delays)

    def polite_get(url, **options):
        if routes is None or len(routes.exits) < 2:
            throttle.wait(url)
            return get(url, **{**defaults, **options})
        host, first = urlparse(url).netloc, None
        for position, exit_ in enumerate(routes.order(host)):
            throttle.wait(url, lane=exit_.name)
            asked = {**defaults, **options, "proxy": exit_.proxy}
            if position:
                asked["tries"] = 1
            try:
                body = get(url, **asked)
            except Exception as error:
                if not refused(error, exit_.proxy is not None):
                    raise
                first = first or error
                continue
            routes.worked(host, exit_)
            return body
        raise first
    polite_get.throttle = throttle
    polite_get.routes = routes
    return polite_get

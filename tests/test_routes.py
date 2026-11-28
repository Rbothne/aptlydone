"""A site that refuses one exit is asked through the next, and the exit that answered is remembered for it."""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from aptrack import fetch, vpn


def refusal(url, code=403):
    return urllib.error.HTTPError(url, code, "refused", {}, io.BytesIO(b""))


class FakeGet:
    """Stands in for fetch.get: answers by exit (its proxy), from a table {proxy: body or status code}."""

    def __init__(self, table):
        self.table, self.asked = table, []

    def __call__(self, url, proxy=None, **options):
        self.asked.append((proxy, options.get("tries")))
        answer = self.table[proxy]
        if answer == 429:
            raise fetch.RateLimited(url)
        if answer == 404:
            raise fetch.Gone(url)
        if isinstance(answer, int):
            raise refusal(url, answer)
        if isinstance(answer, Exception):
            raise answer
        return answer


EXITS = [vpn.Exit("direct"), vpn.Exit("warp", "http://127.0.0.1:1"), vpn.Exit("wg-ca", "http://127.0.0.1:2")]


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "routes.json")

    def routed(self, table, where="local"):
        routes = fetch.Routes(EXITS, self.path, where=where, today="2026-11-27")
        fake = FakeGet(table)
        with mock.patch.object(fetch, "get", fake):
            get = fetch.polite(0.0, routes=routes)
            return get, fake, routes

    def call(self, get, fake, url="https://a.test/x"):
        with mock.patch.object(fetch, "get", fake):
            return get(url)

    def test_a_refused_site_is_asked_through_the_next_exit_once(self):
        get, fake, _ = self.routed({None: 403, "http://127.0.0.1:1": b"ok", "http://127.0.0.1:2": b"never"})
        self.assertEqual(self.call(get, fake), b"ok")
        self.assertEqual(fake.asked, [(None, None), ("http://127.0.0.1:1", 1)])

    def test_the_exit_that_answered_is_kept_and_tried_first_next_run(self):
        get, fake, _ = self.routed({None: 403, "http://127.0.0.1:1": 403, "http://127.0.0.1:2": b"ok"})
        self.call(get, fake)
        saved = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(saved, {"local": {"a.test": {"exit": "wg-ca", "at": "2026-11-27"}}})
        get, fake, _ = self.routed({None: b"never", "http://127.0.0.1:1": b"never", "http://127.0.0.1:2": b"ok"})
        self.assertEqual(self.call(get, fake), b"ok")
        self.assertEqual(fake.asked, [("http://127.0.0.1:2", None)])

    def test_routes_are_kept_apart_for_github_and_this_machine(self):
        get, fake, _ = self.routed({None: 403, "http://127.0.0.1:1": b"ok", "http://127.0.0.1:2": b"x"}, where="github")
        self.call(get, fake)
        get, fake, _ = self.routed({None: b"home", "http://127.0.0.1:1": b"x", "http://127.0.0.1:2": b"x"}, where="local")
        self.assertEqual(self.call(get, fake), b"home")
        self.assertEqual(fake.asked, [(None, None)])

    def test_a_site_answering_directly_again_forgets_its_route(self):
        os.makedirs(self.folder, exist_ok=True)
        json.dump({"local": {"a.test": {"exit": "warp", "at": "2026-11-20"}}}, open(self.path, "w"))
        get, fake, _ = self.routed({None: b"ok", "http://127.0.0.1:1": 403, "http://127.0.0.1:2": 403})
        self.assertEqual(self.call(get, fake), b"ok")
        self.assertEqual(json.load(open(self.path)), {"local": {}})

    def test_gone_is_gone_everywhere(self):
        get, fake, _ = self.routed({None: 404, "http://127.0.0.1:1": b"x", "http://127.0.0.1:2": b"x"})
        with self.assertRaises(fetch.Gone):
            self.call(get, fake)
        self.assertEqual(len(fake.asked), 1)

    def test_every_exit_refusing_raises_the_first_refusal(self):
        get, fake, _ = self.routed({None: 403, "http://127.0.0.1:1": 429, "http://127.0.0.1:2": OSError("tunnel down")})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.call(get, fake)
        self.assertEqual(caught.exception.code, 403)

    def test_a_connection_failure_on_our_own_address_is_not_a_refusal(self):
        get, fake, _ = self.routed({None: urllib.error.URLError("no route"), "http://127.0.0.1:1": b"x", "http://127.0.0.1:2": b"x"})
        with self.assertRaises(urllib.error.URLError):
            self.call(get, fake)

    def test_without_exits_it_behaves_as_before(self):
        fake = FakeGet({None: b"plain"})
        with mock.patch.object(fetch, "get", fake):
            self.assertEqual(fetch.polite(0.0)("https://a.test/"), b"plain")


class RefusalIsNotRepeatedTests(unittest.TestCase):
    def test_403_is_raised_at_once(self):
        calls = []

        def opener(request, timeout=None):
            calls.append(1)
            raise refusal(request.full_url)
        with self.assertRaises(urllib.error.HTTPError):
            fetch.get("https://a.test/", opener=opener, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)


class ConfigTests(unittest.TestCase):
    def test_configs_in_one_secret_are_split_on_dashes(self):
        text = "[Interface]\nPrivateKey = a\n[Peer]\nEndpoint = 1.2.3.4:51820\n---\n[Interface]\nPrivateKey = b\n---\n\n"
        confs = vpn.split_confs(text)
        self.assertEqual(len(confs), 2)
        self.assertIn("PrivateKey = b", confs[1])

    def test_endpoint_is_replaced(self):
        out = vpn.with_endpoint("[Peer]\nEndpoint = engage.cloudflareclient.com:2408\nAllowedIPs = 0.0.0.0/0", "162.159.192.1:500")
        self.assertIn("Endpoint = 162.159.192.1:500", out)
        self.assertNotIn("2408", out)

    def test_off_leaves_only_direct(self):
        exits = vpn.open_exits(environ={"APTRACK_VPN": "off"}, say=lambda *a: None)
        self.assertEqual([e.name for e in exits], ["direct"])

    def test_every_platform_has_pinned_tools(self):
        for platform in ("win32", "linux"):
            for name in ("wireproxy", "wgcf"):
                self.assertRegex(vpn.TOOLS[(platform, name)]["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()

"""Exits: other ways out to the internet, for sites that refuse the address a run starts from.

The idea is the owner's catalogue's (`active_projects/catalog`, `catalog/vpn.py`): an app-scoped WireGuard tunnel
run by wireproxy (userspace WireGuard, no admin rights, no system routes; nothing else on the machine goes through
it), brought up with the run and taken down with it. Here each tunnel exposes an HTTP proxy port that
`fetch.get(proxy=...)` sends a request through, and `fetch.Routes` remembers which exit each site answered
through, between runs (`data/routes.json`, on the data branch).

The exits, tried in this order for a site with no route learned yet:

    direct      the run's own address (this machine's connection, or the GitHub runner's)
    warp        Cloudflare WARP, free and without an account: wgcf registers a device the first time. A WARP_PROFILE
                environment variable (the text of a wgcf-profile.conf, e.g. a GitHub secret) reuses one identity.
                Locally the registration is kept in .vpn/warp/
    wg-<name>   each WireGuard config in .vpn/wg/*.conf, and each in APTRACK_WG_CONFS (config texts separated by a
                line `---`, e.g. a GitHub secret holding Proton VPN Free configs)
    proxy-<n>   each address in APTRACK_PROXIES (comma-separated http:// proxies: a home connection over a tailnet,
                say)

APTRACK_VPN=off leaves only `direct`. A tunnel that does not come up is reported and skipped: the run goes on with
the exits it has.

What a tunnel changes is the address a site sees. A site that challenges an address (HTTP 403 with
`cf-mitigated: challenge`) may let another through; one that challenges every data-centre and VPN address will
not be opened this way. Measured on 2026-11-27 from this machine: see sources-unread.md.
"""

import atexit
import hashlib
import io
import os
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("APTRACK_VPN_DIR") or ROOT / ".vpn")
TRACE = "https://www.cloudflare.com/cdn-cgi/trace"

# Pinned by SHA-256: the Windows ones as checked by the catalogue, the Linux ones from the digests GitHub publishes
# for each release asset (wireproxy v1.1.3, wgcf v2.3.1).
TOOLS = {
    ("win32", "wireproxy"): {"url": "https://github.com/windtf/wireproxy/releases/download/v1.1.3/wireproxy_windows_amd64.tar.gz",
                             "sha256": "bce041ea9fe0f8a3351301dcbe29cdf6a523bb25cf9c62f17ebb5699a8051d0f", "member": "wireproxy.exe"},
    ("linux", "wireproxy"): {"url": "https://github.com/windtf/wireproxy/releases/download/v1.1.3/wireproxy_linux_amd64.tar.gz",
                             "sha256": "e88c1d090740373fc606c1bafd81d9a5eadc642cce5667616e20e9d7a444f51c", "member": "wireproxy"},
    ("win32", "wgcf"): {"url": "https://github.com/ViRb3/wgcf/releases/download/v2.3.1/wgcf_2.3.1_windows_amd64.exe",
                        "sha256": "e222fd9443d7cb3264d825a3e86967797fc9c938507c5d93e3cc21e4aed11dcc"},
    ("linux", "wgcf"): {"url": "https://github.com/ViRb3/wgcf/releases/download/v2.3.1/wgcf_2.3.1_linux_amd64",
                        "sha256": "4fb7a136aa470ece11d17949c7db07b040ec9c604742dc8680bcf1889f85d0c8"},
}
# WARP answers on several addresses and UDP ports; some networks drop one but not another (the catalogue's list).
WARP_ENDPOINTS = ["engage.cloudflareclient.com:2408", "162.159.192.1:2408", "162.159.193.1:2408", "162.159.192.1:500",
                  "162.159.192.1:4500", "162.159.192.1:1701", "162.159.195.1:2408", "162.159.192.1:8854"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class TunnelError(RuntimeError):
    pass


class Exit:
    """One way out: `proxy` is None for the run's own connection, else the tunnel's HTTP proxy address."""

    def __init__(self, name, proxy=None, process=None, address=None):
        self.name, self.proxy, self.process, self.address = name, proxy, process, address

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def __repr__(self):
        return f"Exit({self.name!r}, {self.proxy!r})"


def _platform():
    return "win32" if sys.platform == "win32" else "linux"


def tool(name, home=HOME):
    """The path of a helper binary, downloaded (and its SHA-256 checked) the first time it is needed."""
    spec = TOOLS[(_platform(), name)]
    folder = home / "tools"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + (".exe" if _platform() == "win32" else ""))
    mark = folder / (name + ".sha256")
    if path.exists() and mark.exists() and mark.read_text().strip() == spec["sha256"]:
        return path
    with urllib.request.urlopen(spec["url"], timeout=60) as response:
        blob = response.read()
    if hashlib.sha256(blob).hexdigest() != spec["sha256"]:
        raise TunnelError(f"{spec['url']} did not match its pinned SHA-256; not used")
    if spec.get("member"):
        with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
            member = next(m for m in tar.getmembers() if Path(m.name).name == spec["member"])
            blob = tar.extractfile(member).read()
    path.write_bytes(blob)
    path.chmod(0o755)
    mark.write_text(spec["sha256"])
    return path


def warp_profile(home=HOME, environ=os.environ):
    """A wgcf-profile.conf: WARP_PROFILE's text, the one registered before, or a new free registration."""
    folder = home / "warp"
    folder.mkdir(parents=True, exist_ok=True)
    profile = folder / "wgcf-profile.conf"
    given = (environ.get("WARP_PROFILE") or "").strip()
    if given:
        profile.write_text(given + "\n", encoding="utf-8")
        return profile
    if profile.exists():
        return profile
    wgcf = str(tool("wgcf", home))
    for args in (["register", "--accept-tos"], ["generate"]):
        if args[0] == "register" and (folder / "wgcf-account.toml").exists():
            continue
        done = subprocess.run([wgcf, *args], cwd=folder, capture_output=True, text=True, timeout=90, creationflags=NO_WINDOW)
        if done.returncode != 0:
            raise TunnelError(f"wgcf {args[0]} failed: {(done.stderr or done.stdout).strip()[-300:]}")
    if not profile.exists():
        raise TunnelError("wgcf did not write wgcf-profile.conf")
    return profile


def with_endpoint(conf_text, endpoint):
    """The same WireGuard config, pointed at another endpoint."""
    return "\n".join(f"Endpoint = {endpoint}" if line.strip().lower().startswith("endpoint") else line
                     for line in conf_text.splitlines()) + "\n"


def split_confs(text):
    """APTRACK_WG_CONFS: WireGuard configs one after another, separated by a line `---`."""
    blocks, current = [], []
    for line in (text or "").splitlines():
        if line.strip() == "---":
            blocks.append("\n".join(current))
            current = []
        else:
            current.append(line)
    blocks.append("\n".join(current))
    return [b.strip() + "\n" for b in blocks if "[Interface]" in b]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def exit_address(proxy, timeout=10):
    """The address a site sees through `proxy` (None: our own), or None when nothing answers through it."""
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    try:
        with urllib.request.build_opener(*handlers).open(TRACE, timeout=timeout) as response:
            text = response.read().decode("utf-8", "replace")
    except Exception:
        return None
    return next((line[3:] for line in text.splitlines() if line.startswith("ip=")), "?")


def start_tunnel(name, conf_path, home=HOME, wait=20.0):
    """Run wireproxy for one WireGuard config with an HTTP proxy port, and check something answers through it."""
    port = free_port()
    folder = home / "run"
    folder.mkdir(parents=True, exist_ok=True)
    conf = folder / f"wireproxy-{name}.conf"
    conf.write_text(f"WGConfig = {Path(conf_path).as_posix()}\n\n[http]\nBindAddress = 127.0.0.1:{port}\n", encoding="utf-8")
    log = open(folder / f"wireproxy-{name}.log", "wb")
    process = subprocess.Popen([str(tool("wireproxy", home)), "-c", str(conf)], cwd=folder, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    log.close()
    proxy = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise TunnelError(f"wireproxy stopped (code {process.returncode}); see {folder / f'wireproxy-{name}.log'}")
        address = exit_address(proxy, timeout=6)
        if address:
            return Exit(name, proxy, process, address)
        time.sleep(1)
    Exit(name, proxy, process).close()
    raise TunnelError("no answer through the tunnel (handshake never completed?)")


def start_warp(home=HOME, environ=os.environ):
    base = warp_profile(home, environ).read_text(encoding="utf-8")
    active = home / "warp" / "wgcf-profile.active.conf"
    last = None
    for endpoint in WARP_ENDPOINTS:
        active.write_text(with_endpoint(base, endpoint), encoding="utf-8")
        try:
            return start_tunnel("warp", active, home, wait=12)
        except TunnelError as error:
            last = error
    raise TunnelError(f"no WARP endpoint answered (UDP blocked here?): {last}")


def open_exits(home=HOME, environ=os.environ, say=print):
    """Every exit this run can use, `direct` first. Tunnels close when the program ends."""
    exits = [Exit("direct")]
    if (environ.get("APTRACK_VPN") or "").strip().lower() in ("off", "0", "no", "false"):
        say("exits: direct only (APTRACK_VPN is off)")
        return exits
    starters = [("warp", lambda: start_warp(home, environ))]
    confs = sorted((home / "wg").glob("*.conf")) if (home / "wg").is_dir() else []
    for path in confs:
        starters.append((f"wg-{path.stem}", lambda p=path: start_tunnel(f"wg-{p.stem}", p, home)))
    for n, text in enumerate(split_confs(environ.get("APTRACK_WG_CONFS")), 1):
        written = home / "run" / f"secret-{n}.conf"
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(text, encoding="utf-8")
        starters.append((f"wg-secret-{n}", lambda p=written, n=n: start_tunnel(f"wg-secret-{n}", p, home)))
    for name, start in starters:
        try:
            exit_ = start()
        except Exception as error:                  # a missing tunnel costs that exit, never the run
            say(f"exits: {name} did not come up: {error}")
            continue
        atexit.register(exit_.close)
        exits.append(exit_)
        say(f"exits: {name} up, sites see {exit_.address}")
    for n, proxy in enumerate(p.strip() for p in (environ.get("APTRACK_PROXIES") or "").split(",") if p.strip()):
        address = exit_address(proxy)
        if address:
            exits.append(Exit(f"proxy-{n + 1}", proxy, address=address))
            say(f"exits: proxy-{n + 1} answers, sites see {address}")
        else:
            say(f"exits: proxy-{n + 1} ({proxy}) did not answer")
    return exits


def routes(path=None, environ=os.environ, say=print):
    """The exits this run has, with the routes learned before (data/routes.json): pass to `fetch.polite(routes=)`."""
    from . import fetch
    return fetch.Routes(open_exits(environ=environ, say=say), str(path or ROOT / "data" / "routes.json"))

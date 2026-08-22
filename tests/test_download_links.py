"""Every link we hand a customer must actually resolve.

Written after a customer hit a 404 on a download link and told us about it —
which is the wrong way round. These pages point at App Store listings, Google
Play, GitHub release assets and vendor sites, none of which we control: an app
can be pulled from a store (the Russian «Happ Proxy Utility Plus» build was)
and a release asset can be renamed, with nothing on our side changing.

Networked on purpose, and skipped rather than failed when there is no way out,
so an offline run does not masquerade as a broken link.
"""
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "web" / "src"
SOURCES = [
    WEB / "app" / "download" / "page.tsx",
    WEB / "app" / "connect" / "ConnectClient.tsx",
]
# Not a download link: the subscription host is ours and answers only to a token.
IGNORE = ("sub.unlockvpn.site",)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"


def collect() -> list[str]:
    found: set[str] = set()
    for path in SOURCES:
        if not path.exists():
            continue
        for url in re.findall(r'https://[^\s"\'`,)]+', path.read_text(encoding="utf-8")):
            url = url.rstrip('",)')
            if not any(skip in url for skip in IGNORE):
                found.add(url)
    return sorted(found)


# Codes that mean "the other side is busy", not "the link is dead". Failing the
# build on a store's rate limiter would teach us to ignore this test, which is
# worse than not having it.
TRANSIENT = {408, 429, 500, 502, 503, 504}


def reach(url: str, timeout: float = 25.0) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


@pytest.mark.integration
def test_every_download_link_resolves():
    urls = collect()
    assert urls, "no links found — the pages moved and this test stopped checking anything"

    broken: list[str] = []
    for url in urls:
        try:
            status = reach(url)
        except Exception as exc:  # no route out of the machine running the tests
            pytest.skip(f"network unavailable ({type(exc).__name__}) — cannot judge {url}")
        if status in TRANSIENT:
            time.sleep(2)  # one patient retry before accusing anyone
            try:
                status = reach(url)
            except Exception:
                continue
            if status in TRANSIENT:
                continue
        if status >= 400:
            broken.append(f"{status} {url}")

    assert not broken, "links we publish are dead:\n  " + "\n  ".join(broken)


@pytest.mark.integration
def test_the_real_happ_is_the_one_we_link():
    """Two impostors — «Happ VPN» and «Happ VPN ++» — sit next to the real app in
    search results. The page warns about them, so the id it links has to be the
    genuine listing and not drift onto one of theirs."""
    try:
        with urllib.request.urlopen(
            "https://itunes.apple.com/lookup?id=6504287215&country=us", timeout=25
        ) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:
        pytest.skip(f"App Store lookup unavailable ({type(exc).__name__})")

    import json

    results = json.loads(body).get("results") or []
    assert results, "the linked App Store listing no longer exists"
    assert results[0]["sellerName"] == "Flyfrog LLC", results[0]["sellerName"]

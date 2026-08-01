"""Hysteresis in the end-to-end node prober."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "node_probe", pathlib.Path(__file__).parent.parent / "scripts" / "node_probe.py"
)
node_probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(node_probe)

apply_hysteresis = node_probe.apply_hysteresis


def test_first_sighting_trusts_the_probe():
    verdicts, streaks = apply_hysteresis({}, {"h1": True, "h2": False})
    assert verdicts == {"h1": True, "h2": False}
    assert streaks == {"h1": 1, "h2": -1}


def test_one_failure_does_not_drop_a_healthy_node():
    """A single timeout on a busy exit is normal; dropping it would churn
    everyone's subscription for nothing."""
    prev = {"nodes": {"h1": True}, "streaks": {"h1": 5}}
    verdicts, streaks = apply_hysteresis(prev, {"h1": False})
    assert verdicts["h1"] is True
    assert streaks["h1"] == -1


def test_two_consecutive_failures_drop_the_node():
    prev = {"nodes": {"h1": True}, "streaks": {"h1": -1}}
    verdicts, _ = apply_hysteresis(prev, {"h1": False})
    assert verdicts["h1"] is False


def test_one_success_does_not_restore_a_flapping_node():
    """The Amsterdam case: it passes the occasional probe while failing most
    real traffic, so a lone success must not put it back in front of users."""
    prev = {"nodes": {"h1": False}, "streaks": {"h1": -4}}
    verdicts, streaks = apply_hysteresis(prev, {"h1": True})
    assert verdicts["h1"] is False
    assert streaks["h1"] == 1


def test_two_consecutive_successes_restore_the_node():
    prev = {"nodes": {"h1": False}, "streaks": {"h1": 1}}
    verdicts, _ = apply_hysteresis(prev, {"h1": True})
    assert verdicts["h1"] is True


def test_streak_resets_direction_on_flip():
    prev = {"nodes": {"h1": True}, "streaks": {"h1": 7}}
    _, streaks = apply_hysteresis(prev, {"h1": False})
    assert streaks["h1"] == -1  # not 6 — a failure starts a fresh failure run


def test_flapping_node_stays_dropped_across_alternating_results():
    """Alternating pass/fail must never oscillate the served list."""
    state = {"nodes": {"h1": False}, "streaks": {"h1": -2}}
    for passed in (True, False, True, False, True):
        verdicts, streaks = apply_hysteresis(state, {"h1": passed})
        state = {"nodes": verdicts, "streaks": streaks}
    assert state["nodes"]["h1"] is False


# --- transport handling and per-host aggregation -------------------------------

def _uri(host, port, extra=""):
    return (f"vless://uuid@{host}:{port}?security=reality&sni={host}"
            f"&pbk=P&sid=S&fp=chrome{extra}")


def test_xhttp_link_is_parsed_with_its_transport():
    """Probing an XHTTP endpoint with a plain TCP config always fails, and that
    false negative once pulled healthy nodes from every subscription."""
    node = node_probe.parse_vless(_uri("h1", 2097, "&type=xhttp&path=%2Fabc&mode=auto"))
    assert node["network"] == "xhttp"
    assert node["path"] == "/abc"
    cfg = node_probe.build_config(node, 1080)
    stream = cfg["outbounds"][0]["streamSettings"]
    assert stream["network"] == "xhttp"
    assert stream["xhttpSettings"]["path"] == "/abc"


def test_tcp_link_gets_no_xhttp_block():
    node = node_probe.parse_vless(_uri("h1", 2087))
    cfg = node_probe.build_config(node, 1080)
    stream = cfg["outbounds"][0]["streamSettings"]
    assert stream["network"] == "tcp"
    assert "xhttpSettings" not in stream


def test_host_is_alive_if_any_of_its_entrypoints_works(monkeypatch):
    """One broken transport must not condemn the whole node — assigning per
    link let the last one probed overwrite a working result."""
    calls = []

    def fake_probe(node):
        calls.append((node["host"], node["port"]))
        return node["port"] == 2087  # TCP works, XHTTP does not

    monkeypatch.setattr(node_probe, "probe_node", fake_probe)
    monkeypatch.setattr(node_probe, "fetch_links", lambda url: [
        _uri("h1", 2087), _uri("h1", 2097, "&type=xhttp&path=%2Fx"),
    ])
    monkeypatch.setattr(node_probe, "PROBE_SUB_URL", "https://example/sub")
    monkeypatch.setattr(node_probe.os.path, "exists", lambda p: True)
    written = {}
    monkeypatch.setattr(node_probe, "load_previous", lambda: {})
    monkeypatch.setattr(node_probe.os, "replace", lambda a, b: None)

    real_open = open

    def fake_open(path, mode="r", *a, **kw):
        if "w" in mode:
            import io
            buf = io.StringIO()
            buf.close = lambda: written.update(body=buf.getvalue())
            return buf
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    assert node_probe.main() == 0
    import json as _json
    assert _json.loads(written["body"])["nodes"]["h1"] is True
    assert len(calls) == 2  # both entrypoints were tried


# --- endpoints outside the panel ----------------------------------------------

def test_extra_links_are_probed_alongside_the_subscription(monkeypatch):
    """The Moscow relay is not a Marzban node, yet every 🇷🇺→<country> entry
    terminates on it. Unprobed, it could black-hole the top of every
    subscription indefinitely with nothing noticing."""
    relay = ("vless://uuid@130.49.143.41.sslip.io:2091?security=reality"
             "&sni=130.49.143.41.sslip.io&pbk=P&sid=S&fp=chrome")
    seen = []
    monkeypatch.setattr(node_probe, "PROBE_SUB_URL", "https://example/sub")
    monkeypatch.setattr(node_probe, "PROBE_EXTRA_LINKS", relay)
    monkeypatch.setattr(node_probe, "fetch_links", lambda url: [_uri("h1", 2087)])
    monkeypatch.setattr(node_probe.os.path, "exists", lambda p: True)
    monkeypatch.setattr(node_probe, "load_previous", lambda: {})
    monkeypatch.setattr(node_probe.os, "replace", lambda a, b: None)

    def fake_probe(node):
        seen.append(node["host"])
        return True

    monkeypatch.setattr(node_probe, "probe_node", fake_probe)
    real_open = open

    def fake_open(path, mode="r", *a, **kw):
        if "w" in mode:
            import io
            return io.StringIO()
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    node_probe.main()
    assert "130.49.143.41.sslip.io" in seen, "relay must be probed"
    assert "h1" in seen, "panel nodes must still be probed"


def test_extra_links_accept_comma_or_newline(monkeypatch):
    a = "vless://u@r1:2091?security=reality&sni=r1&pbk=P&sid=S"
    b = "vless://u@r2:2092?security=reality&sni=r2&pbk=P&sid=S"
    for joined in (f"{a},{b}", f"{a}\n{b}"):
        monkeypatch.setattr(node_probe, "PROBE_EXTRA_LINKS", joined)
        parsed = [
            part.strip()
            for part in node_probe.PROBE_EXTRA_LINKS.replace(",", "\n").splitlines()
            if part.strip().startswith("vless://")
        ]
        assert len(parsed) == 2

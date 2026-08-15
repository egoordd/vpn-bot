"""Hysteresis in the end-to-end node prober."""
import importlib.util
import json
import pathlib
import time

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


def test_alert_on_node_dropped():
    """Pulling a node silently is how the Amsterdam week happened: the owner
    heard it from customers instead of from us."""
    prev = {"nodes": {"166.0.28.132.sslip.io": True}}
    text, notified = node_probe.compose_alert(prev, {"166.0.28.132.sslip.io": False}, 1000.0)
    assert "Убраны из выдачи" in text
    assert "Германия" in text
    assert notified["166.0.28.132.sslip.io"] == 1000.0


def test_alert_on_node_restored():
    prev = {"nodes": {"78.17.154.225.sslip.io": False}, "notified_at": {"78.17.154.225.sslip.io": 10.0}}
    text, notified = node_probe.compose_alert(prev, {"78.17.154.225.sslip.io": True}, 1000.0)
    assert "Вернулись в выдачу" in text and "Польша" in text
    assert "78.17.154.225.sslip.io" not in notified  # state cleared on recovery


def test_no_message_when_nothing_changed():
    prev = {"nodes": {"h1": True, "h2": True}}
    text, _ = node_probe.compose_alert(prev, {"h1": True, "h2": True}, 1000.0)
    assert text == ""


def test_same_box_under_two_hostnames_is_named_once():
    """The US box is probed bare and as an sslip name; two lines for one
    location reads like two outages."""
    prev = {"nodes": {"144.172.101.217": True, "144.172.101.217.sslip.io": True}}
    text, _ = node_probe.compose_alert(
        prev, {"144.172.101.217": False, "144.172.101.217.sslip.io": False}, 1000.0
    )
    assert text.count("🇺🇸 США") == 1


def test_several_nodes_flip_in_one_message():
    prev = {"nodes": {"166.0.28.132": True, "78.17.154.225": False}}
    text, _ = node_probe.compose_alert(
        prev, {"166.0.28.132": False, "78.17.154.225": True}, 1000.0
    )
    assert "Убраны из выдачи" in text and "Вернулись в выдачу" in text


def test_dead_node_is_not_re_announced_every_run():
    prev = {"nodes": {"h1": False}, "notified_at": {"h1": 900.0}}
    text, _ = node_probe.compose_alert(prev, {"h1": False}, 1000.0)
    assert text == ""


def test_dead_node_is_re_announced_after_the_reminder_window():
    """A location missing for a week must not fade out of attention."""
    prev = {"nodes": {"h1": False}, "notified_at": {"h1": 0.0}}
    text, notified = node_probe.compose_alert(prev, {"h1": False}, node_probe.REMIND_AFTER + 1)
    assert "Всё ещё не работают" in text
    assert notified["h1"] == node_probe.REMIND_AFTER + 1


def test_alert_state_does_not_grow_forever():
    prev = {"nodes": {"h1": False}, "notified_at": {"gone": 5.0, "h1": 5.0}}
    _, notified = node_probe.compose_alert(prev, {"h1": False}, 10.0)
    assert "gone" not in notified


def test_relay_is_named_for_what_its_death_costs():
    """It is not a node — losing it takes out every 🇷🇺→<country> entry."""
    assert "каскад" in node_probe.node_label("130.49.143.41.sslip.io")


def test_unknown_host_falls_back_to_the_host_itself():
    assert node_probe.node_label("1.2.3.4") == "1.2.3.4"


def test_verdicts_are_written_before_the_alert_is_sent(monkeypatch):
    """Telegram being down must never keep a dead exit in subscriptions."""
    order = []
    monkeypatch.setattr(node_probe, "PROBE_SUB_URL", "https://example/sub")
    monkeypatch.setattr(node_probe, "PROBE_EXTRA_LINKS", "")
    monkeypatch.setattr(node_probe, "fetch_links", lambda url: [_uri("166.0.28.132", 2087)])
    monkeypatch.setattr(node_probe.os.path, "exists", lambda p: True)
    monkeypatch.setattr(node_probe, "load_previous", lambda: {"nodes": {"166.0.28.132": True},
                                                             "streaks": {"166.0.28.132": -1}})
    monkeypatch.setattr(node_probe, "probe_node", lambda node: False)
    monkeypatch.setattr(node_probe.os, "replace", lambda a, b: order.append("written"))

    def boom(text):
        order.append("notified")
        raise AssertionError("notify must not be able to break a probe run")

    monkeypatch.setattr(node_probe, "notify", boom)
    real_open = open

    def fake_open(path, mode="r", *a, **kw):
        if "w" in mode:
            import io
            return io.StringIO()
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    try:
        node_probe.main()
    except AssertionError:
        pass
    assert order[0] == "written", "health file must land before Telegram is touched"


def test_broken_prober_alert_is_throttled(monkeypatch):
    """A panel outage fires the probe every 3 minutes; twenty messages an hour
    trains the owner to mute the alerts bot."""
    sent = []
    monkeypatch.setattr(node_probe, "notify", lambda text: sent.append(text))
    monkeypatch.setattr(node_probe, "load_previous",
                        lambda: {"broken_notified_at": time.time() - 60})
    node_probe.report_probe_broken("panel down")
    assert sent == []


def test_broken_prober_alert_fires_when_cooldown_expired(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(node_probe, "notify", lambda text: sent.append(text))
    monkeypatch.setattr(node_probe, "load_previous", lambda: {"broken_notified_at": 0})
    monkeypatch.setattr(node_probe, "HEALTH_FILE", str(tmp_path / "health.json"))
    node_probe.report_probe_broken("panel down")
    assert sent and "не работает" in sent[0]


def test_broken_prober_alert_keeps_existing_verdicts(monkeypatch, tmp_path):
    """The failure is ours, not the nodes' — verdicts must survive untouched so
    the gateway keeps serving what last worked."""
    health = tmp_path / "health.json"
    health.write_text(json.dumps({"checked_at": 123, "nodes": {"h1": True}}))
    monkeypatch.setattr(node_probe, "HEALTH_FILE", str(health))
    monkeypatch.setattr(node_probe, "notify", lambda text: None)
    node_probe.report_probe_broken("panel down")
    saved = json.loads(health.read_text())
    assert saved["nodes"] == {"h1": True} and saved["checked_at"] == 123


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


def test_a_pinned_host_is_not_dropped_on_the_probe_s_word_alone(monkeypatch):
    """The probe judges from one machine on one Russian hosting network, and
    hosting ranges are blocked far more aggressively than consumer ISPs. On
    2026-08-15 Poland failed 127 consecutive rounds — unreachable from the relay,
    ICMP included — while the owner's home ISP reached all three of its ports and
    was actively using it. One blind vantage had removed a working exit from
    every customer's subscription."""
    monkeypatch.setattr(node_probe, "PROBE_PINNED_HOSTS", {"pinned.example"})
    previous = {"nodes": {"pinned.example": True, "other.example": True},
                "streaks": {"pinned.example": -126, "other.example": -1}}
    verdicts, streaks = node_probe.apply_hysteresis(
        previous, {"pinned.example": False, "other.example": False}
    )
    assert verdicts["pinned.example"] is True, "a pinned host stays in subscriptions"
    assert verdicts["other.example"] is False, "everything else still drops normally"
    assert streaks["pinned.example"] == -127, "the failure is still counted, not hidden"


def test_pinning_also_brings_back_a_host_that_was_already_dropped(monkeypatch):
    """A pin that could hold a node in but never bring one back would be useless
    in the situation that motivated it: Poland had already been dropped by the
    time anyone noticed."""
    monkeypatch.setattr(node_probe, "PROBE_PINNED_HOSTS", {"pinned.example"})
    verdicts, _ = node_probe.apply_hysteresis(
        {"nodes": {"pinned.example": False}, "streaks": {"pinned.example": -9}},
        {"pinned.example": False},
    )
    assert verdicts["pinned.example"] is True

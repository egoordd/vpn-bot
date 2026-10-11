"""Сторож AmneziaWG-клиентов на роутерах: пишет только при смене состояния."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "awg_peer_watch", pathlib.Path(__file__).parent.parent / "scripts" / "awg_peer_watch.py"
)
awg_peer_watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(awg_peer_watch)

PUB = "Abc+def/123="
WATCH = {PUB: "Роутер клиента (Якутск)"}
NOW = 1_800_000_000


def test_parses_latest_handshakes_output():
    text = f"{PUB}\t1799999990\nOther=\t0\n\n"
    assert awg_peer_watch.parse_handshakes(text) == {PUB: 1799999990, "Other=": 0}


def test_parses_watch_list_with_base64_keys():
    assert awg_peer_watch.parse_watch(f"{PUB}|Роутер клиента (Якутск); X=|Второй") == {
        PUB: "Роутер клиента (Якутск)",
        "X=": "Второй",
    }


def test_first_run_records_state_without_a_message():
    state, messages = awg_peer_watch.evaluate({}, {PUB: 0}, NOW, WATCH)
    assert state == {PUB: "down"}
    assert messages == []


def test_router_going_silent_is_reported_once():
    stale = NOW - awg_peer_watch.STALE_SECONDS - 60
    state, messages = awg_peer_watch.evaluate({PUB: "up"}, {PUB: stale}, NOW, WATCH)
    assert state == {PUB: "down"}
    assert len(messages) == 1 and "не на связи" in messages[0]

    state, messages = awg_peer_watch.evaluate(state, {PUB: stale}, NOW + 300, WATCH)
    assert messages == []


def test_recovery_is_reported():
    state, messages = awg_peer_watch.evaluate({PUB: "down"}, {PUB: NOW - 30}, NOW, WATCH)
    assert state == {PUB: "up"}
    assert len(messages) == 1 and "снова на связи" in messages[0]


def test_peer_missing_from_server_counts_as_down():
    state, messages = awg_peer_watch.evaluate({PUB: "up"}, {}, NOW, WATCH)
    assert state == {PUB: "down"}
    assert len(messages) == 1

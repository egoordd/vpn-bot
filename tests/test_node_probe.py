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

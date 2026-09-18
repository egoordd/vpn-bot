"""Корпоративные подписки: свои серверы, которые видит только заказчик.

18.09.2026 — отдельный заказ: только финские серверы, «Авто-обход», российские
приложения напрямую, 3 устройства на ссылку. Marzban сам выдаёт новый вход
всем пользователям, поэтому граница проходит по шлюзу: корпоративным ссылкам —
только их серверы, всем остальным — ничего из них.
"""

import base64

import pytest

from services import sub_gateway

FI1 = "78.17.84.88.sslip.io"
FI2 = "89.125.81.96.sslip.io"
PL = "78.17.154.225.sslip.io"


def _vless(host: str, port: int, remark: str) -> str:
    return (
        f"vless://uuid@{host}:{port}?security=reality&type=tcp&flow=xtls-rprx-vision"
        f"&sni={host}&fp=firefox&pbk=k&sid=s#{remark}"
    )


def _token(username: str) -> str:
    head = base64.urlsafe_b64encode(f"{username},1788973596".encode()).decode().rstrip("=")
    return head + "rqtbHlK660"


PANEL_LINKS = "\n".join(
    [_vless(PL, 2087, "PL"), _vless(FI1, 2111, "FI1"), _vless(FI2, 2113, "FI2")]
)


@pytest.fixture
def corp(monkeypatch):
    monkeypatch.setattr(sub_gateway, "CORP_HOSTS", frozenset({FI1, FI2}))
    monkeypatch.setattr(sub_gateway, "CORP_USERS", frozenset({"corp_fi_1"}))
    monkeypatch.setattr(sub_gateway, "HEALTH_ENABLED", False)
    monkeypatch.setattr(sub_gateway, "CASCADE_ENABLED", True)
    monkeypatch.setattr(sub_gateway, "_marzban_sub_active", lambda token: True)
    monkeypatch.setattr(sub_gateway, "_fetch_upstream_sub", lambda token: (PANEL_LINKS, None))


def _hosts(links: list[str]) -> set[str]:
    return {sub_gateway._uri_host(link) for link in links}


def test_regular_user_never_sees_corporate_servers(corp):
    links, _ = sub_gateway.resolve_links(_token("tg_1"))

    assert FI1 not in _hosts(links) and FI2 not in _hosts(links)
    assert PL in _hosts(links)
    assert sub_gateway.RU_RELAY_HOST in _hosts(links), "обычным всё остальное как раньше"


def test_corporate_user_gets_only_its_servers_and_no_shared_extras(corp, monkeypatch):
    monkeypatch.setattr(
        sub_gateway, "NODES", {PL: {**sub_gateway.NODES[PL], "hy2_pass": "pw", "trojan_pass": "pw"}}
    )

    links, _ = sub_gateway.resolve_links(_token("corp_fi_1"))

    assert _hosts(links) == {FI1, FI2}
    assert all(link.startswith("vless://") for link in links), "ни каскада, ни Hy2/Trojan с общим ключом"


def test_corporate_auto_mode_balances_only_between_corporate_servers(corp):
    body, _, is_json = sub_gateway.build_auto_json(_token("corp_fi_1"))

    assert is_json
    assert PL not in body and sub_gateway.RU_RELAY_HOST not in body
    assert FI1 in body and FI2 in body


def test_filter_is_off_until_corporate_hosts_are_configured(monkeypatch):
    monkeypatch.setattr(sub_gateway, "CORP_HOSTS", frozenset())
    links = [_vless(PL, 2087, "PL"), _vless(FI1, 2111, "FI1")]

    assert sub_gateway.corp_filter(links, corporate=False) == links


def test_corporate_links_get_their_own_device_limit(monkeypatch):
    monkeypatch.setattr(sub_gateway, "CORP_USERS", frozenset({"corp_fi_1"}))
    monkeypatch.setattr(sub_gateway, "CORP_DEVICE_LIMIT", 3)
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT_API", "http://127.0.0.1:1/never-called/{telegram_id}")
    sub_gateway._PLAN_LIMITS.clear()

    assert sub_gateway.plan_device_limit("corp_fi_1") == 3

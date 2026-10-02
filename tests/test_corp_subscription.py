"""Корпоративные подписки: свои серверы, которые видит только заказчик.

18.09.2026 — отдельный заказ: только финские серверы, «Авто-обход», российские
приложения напрямую, 3 устройства на ссылку. Marzban сам выдаёт новый вход
всем пользователям, поэтому граница проходит по шлюзу: корпоративным ссылкам —
только их серверы, всем остальным — ничего из них.
"""

import base64
import json
import urllib.parse

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


def test_one_corporate_link_can_get_its_own_device_limit(monkeypatch):
    """03.10.2026: пробная корпоративная ссылка на 20 устройств — без того, чтобы
    поднять лимит действующему заказчику, у которого по договору 3."""
    monkeypatch.setattr(sub_gateway, "CORP_USERS", frozenset({"corp_fi_1", "corp_fi_trial"}))
    monkeypatch.setattr(sub_gateway, "CORP_DEVICE_LIMIT", 3)
    monkeypatch.setattr(sub_gateway, "CORP_DEVICE_LIMITS", sub_gateway._limits("corp_fi_trial:20, мусор, x:abc"))
    sub_gateway._PLAN_LIMITS.clear()

    assert sub_gateway.plan_device_limit("corp_fi_trial") == 20
    assert sub_gateway.plan_device_limit("corp_fi_1") == 3, "остальным — общая цифра"


def test_a_device_limit_for_a_non_corporate_name_changes_nothing(monkeypatch):
    monkeypatch.setattr(sub_gateway, "CORP_USERS", frozenset({"corp_fi_1"}))
    monkeypatch.setattr(sub_gateway, "CORP_DEVICE_LIMITS", {"tg_555": 50})
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT_API", "")
    monkeypatch.setattr(sub_gateway, "DEVICE_LIMIT", 3)

    assert sub_gateway.plan_device_limit("tg_555") == 3


# --- Hysteria2 на корпоративных серверах (18.09.2026) --------------------------
# У каждой корпоративной ссылки свой логин и пароль: общий пароль, как на
# польском узле, не отозвать у одного клиента, когда кончится его срок.


@pytest.fixture
def corp_hy2(corp, monkeypatch):
    monkeypatch.setattr(sub_gateway, "CORP_HY2", {"corp_fi_1": "s3cret-1", "corp_fi_2": "s3cret-2"})
    monkeypatch.setattr(sub_gateway, "CORP_HY2_PORT", 443)


def test_corporate_user_gets_its_own_hysteria_on_every_corporate_server(corp_hy2):
    links, _ = sub_gateway.resolve_links(_token("corp_fi_1"))

    hy2 = [link for link in links if link.startswith("hysteria2://")]
    assert {sub_gateway._uri_host(link) for link in hy2} == {FI1, FI2}
    assert all(link.startswith("hysteria2://corp_fi_1:s3cret-1@") for link in hy2)
    assert f"#{urllib.parse.quote('FI1 · Hysteria2')}" in hy2[0] or f"#{urllib.parse.quote('FI2 · Hysteria2')}" in hy2[0]


def test_nobody_else_ever_sees_corporate_hysteria(corp_hy2):
    regular, _ = sub_gateway.resolve_links(_token("tg_1"))
    other, _ = sub_gateway.resolve_links(_token("corp_fi_2"))

    assert not any("corp_fi_1" in link for link in regular + other)
    assert all(FI1 not in link and FI2 not in link for link in regular)


def test_corporate_hysteria_is_in_the_auto_mode(corp_hy2):
    body, _, _ = sub_gateway.build_auto_json(_token("corp_fi_1"), hysteria=True)

    auto = json.loads(body)[0]
    assert "hysteria" in {outbound.get("protocol") for outbound in auto["outbounds"]}


def test_corporate_auto_mode_loads_on_an_old_core(corp_hy2):
    """The customer runs Happ for Windows 4.3.0: an old core that rejects the
    whole config over a hysteria outbound (2026-09-30)."""
    body, _, _ = sub_gateway.build_auto_json(_token("corp_fi_1"), hysteria=False)

    auto = json.loads(body)[0]
    assert "hysteria" not in {outbound.get("protocol") for outbound in auto["outbounds"]}


def test_corporate_user_without_a_hysteria_login_gets_none(corp_hy2, monkeypatch):
    monkeypatch.setattr(sub_gateway, "CORP_USERS", frozenset({"corp_fi_1", "corp_fi_3"}))

    links, _ = sub_gateway.resolve_links(_token("corp_fi_3"))

    assert links and not any(link.startswith("hysteria2://") for link in links)

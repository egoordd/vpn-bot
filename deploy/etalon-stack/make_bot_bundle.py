"""Сборка бота Etalon для собственной установки заказчика (15.10.2026).

Берёт marat_bot из репозитория и клиент панели, оставляет только тему etalon (темы и картинки
других заказчиков в архив не попадают), заменяет значения по умолчанию, указывавшие на нашу
инфраструктуру, и пишет архив etalon-bot.tgz. Устанавливается в /opt/etalon/bot на главный сервер.

Запуск: python3 deploy/etalon-stack/make_bot_bundle.py <куда положить архив>
"""
from __future__ import annotations

import io
import pathlib
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKIP_THEMES = {"avangard.py", "avangard_strings.py", "classic.py", "orbit.py", "plata.py"}
SKIP_ASSETS = {"avangard", "plata"}

# Замены в копии: (файл, было, стало). Каждая обязана сработать ровно один раз.
PATCHES = [
    ("marat_bot/core.py",
     'SUB_BASE = os.environ.get("MARAT_SUB_BASE", "https://m.212.233.122.241.sslip.io").rstrip("/")',
     'SUB_BASE = os.environ.get("MARAT_SUB_BASE", "").rstrip("/")'),
    ("marat_bot/core.py", 'NAME = os.environ.get("MARAT_NAME", "Марат VPN").strip()',
     'NAME = os.environ.get("MARAT_NAME", "Etalon VPN").strip()'),
    ("marat_bot/webapp.py",
     'DEVICE_DB = os.environ.get("MARAT_DEVICE_DB", "/var/lib/unlock-subgw/devices.sqlite3")',
     'DEVICE_DB = os.environ.get("MARAT_DEVICE_DB", "/var/lib/etalon-gateway/devices.sqlite3")'),
    ("marat_bot/app.py", "    # Иначе — наша панель, доступы основного бота из /opt/vpn-bot/.env.\n",
     "    # Без MARAT_PANEL_URL — настройки панели из config.py (в этой установке не используется).\n"),
    ("marat_bot/texts.py", 'THEME = os.environ.get("MARAT_THEME", "classic").strip() or "classic"',
     'THEME = os.environ.get("MARAT_THEME", "etalon").strip() or "etalon"'),
    ("marat_bot/themes/__init__.py", 'THEMES = ("classic", "orbit", "etalon", "plata", "avangard")', 'THEMES = ("etalon",)'),
    ("marat_bot/themes/__init__.py",
     """MARAT_THEME выбирает тему службы: classic — исходная, orbit — «Ярослав VPN»,
etalon — «Etalon VPN» (бывший «Марат VPN»), plata — «Plata VPN» (бывший «Ярослав VPN»);
avangard — «Avangard VPN» (бывший «Avangard GT», с 14.10 фирменный стиль «Замок», 5 языков);
у etalon, plata и avangard баннеры: BANNERS {экран: файл}.
""",
     """MARAT_THEME выбирает тему службы; в этой установке одна тема — etalon («Etalon VPN»)
с баннерами BANNERS {экран: файл}.
"""),
    ("marat_bot/i18n.py", '"""Языки интерфейса бота (14.10.2026, первым — «Avangard VPN»): ru, en, uk, zh, fa.',
     '"""Языки интерфейса бота: ru, en, uk, zh, fa (используются, если тема многоязычная).'),
    ("marat_bot/i18n.py", "в теме (themes/avangard.py → localized(lang)).", "в теме (localized(lang))."),
    ("marat_bot/core.py", "# Входы панели для новых учёток. У бота на своём Marzban заказчика (Avangard VPN) — свои теги:",
     "# Входы панели для новых учёток — теги входов в xray_config.json панели:"),
    ("marat_bot/core.py", '_DEFAULT_INBOUNDS = "VLESS Reality PL, VLESS Reality FI2, VLESS Reality AMS, VLESS Reality US2"',
     '_DEFAULT_INBOUNDS = "VLESS NL, VLESS DE, VLESS FR"'),
    ("marat_bot/app.py", "        # Свой Marzban заказчика (Avangard VPN): логин его админа из окружения службы.",
     "        # Своя панель Marzban: логин учётки бота из окружения службы."),
    ("marat_bot/core.py",
     """\"\"\"Бот с бесплатным пробным доступом для заказчика (12.10.2026: «Марат VPN», затем «Ярослав VPN»).

Без оплаты, без картинок и без упоминаний основного проекта. Пользователь
получает учётку панели `<префикс><telegram id>` (у Марата `corp_mrt_`, у Ярослава
`corp_yar_`): четыре зарубежных сервера (Польша, Финляндия-2, Нидерланды, США).
Шлюз по шаблону префикса отдаёт её под названием бота: по пункту на страну +
«Авто-обход» + «Режим РУ-сервисов», 2 устройства, свой адрес подписки.
Каждый бот — своя служба с тем же кодом и своим окружением (MARAT_*).""",
     """\"\"\"Бот Etalon VPN: пробный доступ, тарифы, подключение, поддержка.

Пользователь получает учётку панели `<префикс><telegram id>` (MARAT_PREFIX, по умолчанию
`corp_mrt_`) на входах MARAT_INBOUNDS. Шлюз подписок отдаёт её как «⚡️ Авто-выбор»,
«🇷🇺 Режим РУ-сервисов» и по пункту на страну. Настройки — окружение службы (MARAT_*)."""),
    ("marat_bot/core.py",
     "# Один код — несколько ботов для разных заказчиков (12.10.2026: «Марат VPN», «Ярослав VPN»):\n",
     "# Настройки бота задаются окружением службы (/etc/etalon/bot.env):\n"),
]


def _keep(rel: pathlib.PurePosixPath) -> bool:
    parts = rel.parts
    if "__pycache__" in parts or rel.suffix in {".pyc", ".pyo"}:
        return False
    if parts[:2] == ("marat_bot", "themes") and len(parts) == 3 and parts[2] in SKIP_THEMES:
        return False
    if parts[:3] == ("marat_bot", "themes", "assets") and len(parts) > 3 and parts[3] in SKIP_ASSETS:
        return False
    return True


def build(out: pathlib.Path) -> list[str]:
    files = [p for p in (ROOT / "marat_bot").rglob("*") if p.is_file()]
    files += [ROOT / "services" / "__init__.py", ROOT / "services" / "marzban_client.py"]
    patched: dict[str, str] = {}
    for rel, old, new in PATCHES:
        text = patched.get(rel) or (ROOT / rel).read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"замена не сработала: {rel}: {old[:60]}")
        patched[rel] = text.replace(old, new)
    names = []
    with tarfile.open(out, "w:gz") as tar:
        for path in sorted(files):
            rel = pathlib.PurePosixPath(path.relative_to(ROOT).as_posix())
            if not _keep(rel):
                continue
            data = patched[str(rel)].encode() if str(rel) in patched else path.read_bytes()
            info = tarfile.TarInfo(str(rel))
            info.size, info.mode = len(data), 0o644
            tar.addfile(info, io.BytesIO(data))
            names.append(str(rel))
    return names


if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "etalon-bot.tgz")
    names = build(target)
    print(f"{target}: {len(names)} файлов")

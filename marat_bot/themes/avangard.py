"""Тема avangard — «Avangard GT» (13.10.2026). Ни слова об основном проекте.

Гоночный стиль «GT»: графит, карбон, гоночный красный, белые цифры. Каждый основной
экран — баннер (assets/avangard, генератор scripts/make_avangard_banners.py), подпись в
пределах 1024 знаков. Формулировки нейтральные — про скорость и защиту соединения.

14.10.2026: подписки выдаются как у «Etalon VPN» — наша панель, учётки corp_avg_<id>,
4 страны + Авто-обход + Режим РУ-сервисов. Пять языков интерфейса (ru, en, uk, zh, fa):
при первом /start бот спрашивает язык; тексты — в avangard_strings.py, здесь — сборка
экранов под язык (localized). Атрибуты модуля — русский набор (тема по умолчанию).
"""
from __future__ import annotations

import functools
import os
from types import SimpleNamespace

from marat_bot import i18n
from marat_bot.core import DEVICES, NAME, PLANS, TRIAL_DAYS, Access, per_month
from marat_bot.themes.avangard_strings import FLAGS, LANGUAGES, STRINGS
from marat_bot.themes.common import TRIAL_GB, Look, card, escape_name, quote

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "avangard")
BANNERS = {
    screen: os.path.join(_ASSETS, f"{file}.jpg")
    for screen, file in {
        "home": "home", "lang": "home", "issued": "issued", "connect": "connect", "steps": "connect",
        "status": "status", "tariffs": "tariffs", "checkout": "tariffs", "help": "help", "how": "how", "ref": "ref",
    }.items()
}

_DEVICE_BUTTONS = {"dev_ios": "📱 iPhone · iPad", "dev_android": "🤖 Android", "dev_windows": "🖥 Windows",
                   "dev_macos": "💻 Mac"}
_DEVICE_ICONS = {"iPhone / iPad": "📱", "Android": "🤖", "Windows": "🖥", "macOS": "💻"}


def _build(lang: str) -> SimpleNamespace:
    s = STRINGS[lang]
    trial = i18n.days(TRIAL_DAYS, lang)
    look = Look(**s["look"], full="▮", empty="▯")
    ns = SimpleNamespace(LANG=lang, NAME=NAME, TRIAL=trial, LOOK=look, FLAGS=FLAGS, COUNTRIES=s["countries"])

    ns.BUTTONS = {key: value.replace("{trial}", trial) for key, value in s["buttons"].items()} | _DEVICE_BUTTONS

    def welcome(name: str | None = None) -> str:
        safe = escape_name(name)
        return (
            f"<b>{NAME}</b> — {s['tagline']}.\n\n"
            + (s["hello_named"].format(name=safe) if safe else s["hello"])
            + s["welcome_body"] + "\n\n"
            + quote(s["w_servers"].format(flags=FLAGS, countries=s["countries"]), s["w_auto"], s["w_ru"])
            + "\n\n" + s["w_trial"].format(trial=trial, devices=DEVICES)
        )

    def issued(until: str) -> str:
        return (
            s["issued_title"] + "\n\n"
            + quote(s["issued_until"].format(until=until), s["issued_meta"].format(devices=DEVICES, gb_n=TRIAL_GB, gb=s["gb"]))
            + "\n\n" + s["issued_next"]
        )

    def steps(device: str, link: str) -> str:
        return (
            s["steps_title"].format(icon=_DEVICE_ICONS.get(device, "📲"), device=device) + "\n\n"
            + "\n".join((s["step1"], s["step2"], s["step3"])) + "\n\n"
            + quote(s["fallback_title"], s["fallback_text"], f"<code>{link}</code>", expandable=True)
        )

    def status(access: Access, link: str) -> str:
        return s["status_title"] + "\n\n" + quote(*card(access, look, lang)) + f"\n\n{s['status_link']}\n<code>{link}</code>"

    def home(access: Access | None, name: str | None = None) -> str:
        if access is None:
            return welcome(name)
        lines = card(access, look, lang)[1:]
        if access.active:
            return s["home_active"].format(name=NAME) + "\n\n" + quote(*lines) + "\n\n" + s["home_active_hint"]
        return s["home_expired"].format(name=NAME) + "\n\n" + quote(*lines) + "\n\n" + s["home_expired_hint"]

    def plan_label(days: int, default: str = "") -> str:
        return s["plans"].get(days, default)

    def tariffs() -> str:
        rows = [
            s["tariffs_row"].format(label=plan_label(days, label), price=price)
            + (s["tariffs_per"].format(per=per_month(days, price)) if days > 31 else "")
            for days, label, price in PLANS
        ]
        return s["tariffs_title"] + "\n\n" + quote(*rows) + "\n\n" + s["tariffs_each"].format(flags=FLAGS)

    def checkout(label: str, price: int) -> str:
        return (
            s["checkout_title"] + "\n\n"
            + quote(s["checkout_plan"].format(label=label), s["checkout_sum"].format(price=price))
            + "\n\n" + s["checkout_soon"].format(trial=trial)
        )

    def referral(link: str) -> str:
        return s["referral"].format(link=link)

    guide = quote(*s["command_lines"])

    def help_text(telegram_id: int) -> str:
        return (
            s["help_title"] + "\n\n" + s["help_commands"] + "\n" + guide
            + "\n\n" + s["help_modes"] + "\n"
            + quote(s["mode_auto"], s["mode_ru"], s["mode_country"].format(flags=FLAGS))
            + "\n\n" + s["help_broken"] + "\n"
            + quote(s["fix1"], s["fix2"], s["fix3"], s["fix4"], expandable=True)
            + "\n\n" + s["your_id"].format(id=telegram_id)
        )

    ns.welcome, ns.issued, ns.steps, ns.status, ns.home = welcome, issued, steps, status, home
    ns.tariffs, ns.checkout, ns.referral, ns.help_text, ns.plan_label = tariffs, checkout, referral, help_text, plan_label
    ns.COMMANDS_GUIDE = guide
    ns.ALREADY = s["already"]
    ns.PICK_DEVICE = s["pick_device"]
    ns.HOW_IT_WORKS = (
        s["how_title"] + "\n\n" + s["how_text"] + "\n\n"
        + quote(s["how_app"], s["how_link"], s["how_trial"].format(trial=trial, devices=DEVICES, gb_n=TRIAL_GB, gb=s["gb"]))
    )
    ns.SHORT_DESCRIPTION = s["short_description"].format(name=NAME, trial=trial)
    ns.DESCRIPTION = s["description"].format(name=NAME, countries=s["countries"], trial=trial)
    for key in ("support", "news", "promo", "review", "link", "pay"):
        setattr(ns, f"STUB_{key.upper()}", s[f"stub_{key}"])
    ns.NEED_ACCESS = s["need_access"]
    ns.ERROR = s["error"]
    ns.COMMAND_MENU = s["commands"]
    ns.LANG_PROMPT = s["lang_prompt"]
    ns.LANG_SET = s["lang_set"]
    ns.SUPPORT_PROMPT = s["support_prompt"]
    ns.SUPPORT_SENT = s["support_sent"]
    ns.SUPPORT_LIMIT = s["support_limit"]
    ns.SUPPORT_FAILED = s["support_failed"]
    ns.SUPPORT_ANSWER = s["support_answer"]
    ns.date_text = functools.partial(i18n.date_text, lang=lang)
    # Надписи на баннерах — на языке человека: русский в корне assets/avangard, остальные в подпапках.
    folder = _ASSETS if lang == "ru" else os.path.join(_ASSETS, lang)
    ns.BANNERS = {screen: os.path.join(folder, os.path.basename(path)) for screen, path in BANNERS.items()}
    return ns


@functools.lru_cache(maxsize=None)
def localized(lang: str) -> SimpleNamespace:
    return _build(lang if lang in STRINGS else "ru")


# Тема по умолчанию (русский): те же имена на уровне модуля — их проверяет INTERFACE.
globals().update({key: value for key, value in vars(localized("ru")).items() if key not in ("LANG",)})

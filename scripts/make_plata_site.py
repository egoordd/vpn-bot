"""Сайт-визитка «Plata VPN» с документами для ЮKassa (13.10.2026).

ЮKassa проверяет бота @plataavpn_bot: нужны пользовательское соглашение, политика
конфиденциальности, контакты поддержки и понятные тарифы — всегда доступные по ссылкам.
Сайта у заказчика нет, поэтому это небольшая статика в его фирменных цветах (кремовый,
тёмно-синий щит, янтарный шеврон): главная + /tariffs/, /terms/, /privacy/, /support/.
Бот ссылается на эти страницы кнопкой «📄 Документы» (MARAT_SITE_URL).

Тексты — по шаблонам Platega/ЮKassa (как у Etalon), без реквизитов: их добавим, когда
заказчик пришлёт ФИО/статус/ИНН (REQUISITES ниже).

Запуск: python3 scripts/make_plata_site.py  → sites/plata-web/out/
"""
from __future__ import annotations

import html
import os
import shutil

NAME = "Plata VPN"
BOT = "plataavpn_bot"
SITE = "https://plata.168.113.210.6.sslip.io"
UPDATED = "13 октября 2026 г."
SUPPORT_EMAIL = ""  # заполнить, когда заказчик пришлёт
REQUISITES: list[str] = []  # «Самозанятый: ФИО», «ИНН: …» — когда пришлёт заказчик
REPLY_HOURS = 24
TRIAL = {"days": "3 дня", "devices": 2, "gb": 10}
DEVICES = 5
PLANS = [("1 месяц", 30, 199), ("3 месяца", 90, 549), ("6 месяцев", 180, 999), ("12 месяцев", 365, 1799)]
COUNTRIES = "Польша, Финляндия, Нидерланды, США"

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sites", "plata-web", "out")
BOT_LINK = f"https://t.me/{BOT}"
SUPPORT_LINK = f"https://t.me/{BOT}?start=support"

LOGO = (
    '<svg class="logo__mark" viewBox="0 0 64 72" aria-hidden="true">'
    '<defs><linearGradient id="amb" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#F7C866"/><stop offset="1" stop-color="#F2A448"/></linearGradient></defs>'
    '<path d="M32 2 58 11v22c0 18-11 31-26 37C17 64 6 51 6 33V11Z" fill="#172854"/>'
    '<path d="M15 41 32 26l17 15" fill="none" stroke="url(#amb)" stroke-width="8" stroke-linecap="round" '
    'stroke-linejoin="round"/></svg>'
)

CSS = """
:root{--cream:#FEF8EC;--cream-2:#FBEFD9;--navy:#172854;--navy-2:#24376B;--ink:#172854;--soft:#4F5B7A;
--dim:#7C86A0;--amber:#F2A448;--amber-l:#F7C866;--line:rgb(23 40 84/.12);--white:#fff;
--r:22px;--max:1080px;--shadow:0 1px 2px rgb(23 40 84/.06),0 18px 40px -24px rgb(23 40 84/.35)}
*,*::before,*::after{box-sizing:border-box}*{margin:0}
html{-webkit-text-size-adjust:100%}
body{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
font-size:clamp(1rem,.96rem + .2vw,1.06rem);line-height:1.65;color:var(--ink);
background:radial-gradient(70% 50% at 85% 0%,var(--cream-2),transparent 70%),var(--cream);min-height:100dvh}
a{color:inherit}
.wrap{width:100%;max-width:var(--max);margin-inline:auto;padding-inline:clamp(16px,4vw,40px)}
header.top{position:sticky;top:0;z-index:10;background:rgb(254 248 236/.86);backdrop-filter:blur(12px);
-webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.top__row{display:flex;align-items:center;gap:20px;min-height:68px}
.logo{display:inline-flex;align-items:center;gap:10px;text-decoration:none;font-weight:800;font-size:1.2rem;
letter-spacing:-.01em}
.logo__mark{width:28px;height:32px}
.top nav{margin-left:auto;display:flex;gap:6px 22px;flex-wrap:wrap;align-items:center}
.top nav a{text-decoration:none;color:var(--soft);font-size:.95rem}
.top nav a:hover,.top nav a[aria-current=page]{color:var(--navy)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:12px 22px;border-radius:999px;
background:var(--navy);color:var(--white)!important;text-decoration:none;font-weight:700;
box-shadow:var(--shadow);transition:transform .2s ease,background .2s ease}
.btn:hover{background:var(--navy-2);transform:translateY(-1px)}
.btn:focus-visible,a:focus-visible{outline:3px solid var(--amber);outline-offset:3px}
.btn--amber{background:linear-gradient(135deg,var(--amber-l),var(--amber));color:var(--navy)!important}
.btn--sm{padding:9px 16px;font-size:.92rem}
main{padding-block:clamp(36px,6vw,72px)}
h1{font-size:clamp(2rem,1.4rem + 2.6vw,3.2rem);line-height:1.08;letter-spacing:-.02em}
h2{font-size:clamp(1.3rem,1.1rem + .8vw,1.7rem);line-height:1.2;margin-top:2.4rem}
h1+p,.lead{margin-top:14px;color:var(--soft);font-size:1.12em;max-width:60ch}
.updated{margin-top:10px;color:var(--dim);font-size:.9rem}
.doc{max-width:74ch}
.doc p,.doc ul{margin-top:12px;color:var(--soft)}
.doc ul{padding-left:1.2em}.doc li+li{margin-top:6px}
.doc strong{color:var(--ink)}
.doc a{color:var(--navy);font-weight:600;text-decoration-color:var(--amber);text-underline-offset:3px}
.note{margin-top:16px;padding:18px 22px;border-radius:var(--r);background:var(--white);border:1px solid var(--line);
box-shadow:var(--shadow);color:var(--ink)!important}
.hero{display:grid;grid-template-columns:1.2fr .8fr;gap:40px;align-items:center}
.hero__card{padding:28px;border-radius:28px;background:var(--navy);color:var(--cream);box-shadow:var(--shadow)}
.hero__card ul{list-style:none;padding:0;display:grid;gap:12px}
.hero__card li::before{content:"✓";color:var(--amber-l);font-weight:800;margin-right:10px}
.actions{display:flex;flex-wrap:wrap;gap:14px;margin-top:26px}
.plans{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:18px}
.plan{padding:22px;border-radius:var(--r);background:var(--white);border:1px solid var(--line);box-shadow:var(--shadow)}
.plan b{display:block;font-size:.85rem;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
.plan .price{font-size:1.9rem;font-weight:800;margin-top:6px}
.plan small{color:var(--soft)}
table{width:100%;border-collapse:collapse;margin-top:16px;background:var(--white);border-radius:var(--r);overflow:hidden;
box-shadow:var(--shadow)}
th,td{padding:14px 16px;text-align:left;border-bottom:1px solid var(--line)}
th{font-size:.8rem;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
td:nth-child(2){font-weight:800}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:18px;counter-reset:s}
.steps div{padding:20px;border-radius:var(--r);background:var(--white);border:1px solid var(--line)}
.steps div::before{counter-increment:s;content:counter(s);display:inline-grid;place-items:center;width:30px;height:30px;
border-radius:50%;background:linear-gradient(135deg,var(--amber-l),var(--amber));font-weight:800;margin-bottom:10px}
footer{border-top:1px solid var(--line);padding:28px 0 36px;color:var(--dim);font-size:.9rem}
footer nav{display:flex;flex-wrap:wrap;gap:8px 22px;margin-bottom:12px}
footer a{color:var(--soft)}
@media (max-width:860px){.hero{grid-template-columns:1fr}.plans{grid-template-columns:repeat(2,1fr)}
.steps{grid-template-columns:1fr}.top nav a.hide-sm{display:none}}
@media (max-width:480px){.plans{grid-template-columns:1fr}th:nth-child(3),td:nth-child(3){display:none}}
"""

NAV = [("/tariffs/", "Тарифы"), ("/terms/", "Соглашение"), ("/privacy/", "Конфиденциальность"), ("/support/", "Поддержка")]
DOCS = [("/tariffs/", "Тарифы и оплата"), ("/terms/", "Пользовательское соглашение"),
        ("/privacy/", "Политика конфиденциальности"), ("/support/", "Поддержка")]


def per_month(days: int, price: int) -> int:
    return int(price * 30 / days + 0.5)  # как в боте (marat_bot.core.per_month)


def page(path: str, title: str, body: str, description: str) -> str:
    nav = "".join(
        f'<a href="{href}" class="hide-sm"{" aria-current=page" if href == path else ""}>{label}</a>'
        for href, label in NAV
    )
    docs = "".join(f'<a href="{href}">{label}</a>' for href, label in DOCS)
    full_title = NAME if path == "/" else f"{title} · {NAME}"
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title><meta name="description" content="{html.escape(description)}">
<meta name="theme-color" content="#FEF8EC"><link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/style.css"></head>
<body><header class="top"><div class="wrap top__row"><a class="logo" href="/">{LOGO}<span>{NAME}</span></a>
<nav aria-label="Разделы">{nav}<a class="btn btn--sm" href="{BOT_LINK}" target="_blank" rel="noopener noreferrer">Открыть бота</a></nav>
</div></header>
<main id="main"><div class="wrap">{body}</div></main>
<footer><div class="wrap"><nav aria-label="Документы">{docs}</nav>
<p>© 2026 {NAME} · Telegram-бот <a href="{BOT_LINK}">@{BOT}</a> · Редакция документов от {UPDATED}</p>
{"".join(f"<p>{html.escape(r)}</p>" for r in REQUISITES)}</div></footer>
</body></html>
"""


def contact_line() -> str:
    email = f' или по почте <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>' if SUPPORT_EMAIL else ""
    return (f'кнопка «💬 Поддержка» в боте <a href="{SUPPORT_LINK}" target="_blank" rel="noopener noreferrer">'
            f"@{BOT}</a>{email}")


def home() -> str:
    plans = "".join(
        f'<div class="plan"><b>{label}</b><div class="price">{price:,} ₽</div>'.replace(",", " ")
        + f"<small>{per_month(days, price)} ₽ в месяц</small></div>"
        for label, days, price in PLANS
    )
    body = f"""
<section class="hero"><div><h1>Безопасный и быстрый интернет на телефоне и компьютере</h1>
<p>{NAME} шифрует соединение и ведёт его через серверы в Европе и США. Подключение — за минуту через Telegram-бота
и приложение Happ.</p>
<div class="actions"><a class="btn btn--amber" href="{BOT_LINK}" target="_blank" rel="noopener noreferrer">Попробовать
{TRIAL["days"]} бесплатно</a><a class="btn" href="/tariffs/">Тарифы и оплата</a></div></div>
<div class="hero__card"><ul><li>Серверы: {COUNTRIES}</li><li>Авто-обход сам держит самый быстрый сервер</li>
<li>Режим РУ-сервисов: банки и Госуслуги без отключения VPN</li><li>До {DEVICES} устройств на одной подписке</li>
<li>iPhone, Android, Windows, Mac</li></ul></div></section>
<h2>Тарифы</h2><div class="plans">{plans}</div>
<p class="lead">Оплата разовая, без автосписаний. Пробный период — {TRIAL["days"]}, до {TRIAL["devices"]} устройств и
{TRIAL["gb"]} ГБ, без оплаты.</p>
<h2>Как подключиться</h2><div class="steps"><div>Откройте бота <a href="{BOT_LINK}">@{BOT}</a> и получите доступ</div>
<div>Установите приложение Happ — ссылка придёт в боте</div><div>Нажмите «Добавить в Happ» и включите VPN</div></div>
"""
    return page("/", NAME, body, f"{NAME} — безопасный и быстрый интернет. Тарифы, документы и поддержка.")


def tariffs() -> str:
    rows = "".join(
        f"<tr><td>{label}</td><td>{price:,} ₽</td><td>{per_month(days, price)} ₽/мес</td></tr>".replace(",", " ")
        for label, days, price in PLANS
    )
    body = f"""<div class="doc"><h1>Тарифы и оплата</h1><p class="updated">Редакция от {UPDATED}. Цены в рублях.</p>
<table><thead><tr><th>Срок</th><th>Цена</th><th>В месяц</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Что входит в любой тариф</h2><ul><li>доступ ко всем серверам: {COUNTRIES};</li>
<li>Авто-обход — автоматический выбор самого быстрого сервера;</li>
<li>режим РУ-сервисов — российские сайты и приложения открываются напрямую;</li>
<li>до {DEVICES} устройств на одной подписке: iPhone, iPad, Android, Windows, macOS;</li><li>поддержка в Telegram-боте.</li></ul>
<h2>Как проходит оплата</h2><ul><li>в боте <a href="{BOT_LINK}">@{BOT}</a> откройте «💳 Тарифы» и выберите срок;</li>
<li>оплатите банковской картой, через СБП или SberPay на защищённой странице платёжного сервиса;</li>
<li>после подтверждения платежа подписка продлевается на оплаченный срок, ссылка для подключения не меняется.</li></ul>
<p class="note">Оплата разовая: автоматических списаний нет. Перед оплатой бот показывает тариф и итоговую сумму.</p>
<h2>Пробный период</h2><p>{TRIAL["days"]} бесплатно, до {TRIAL["devices"]} устройств и {TRIAL["gb"]} ГБ трафика — без оплаты.
Один раз на аккаунт Telegram.</p>
<h2>Возврат</h2><p>Условия — в разделе 7 <a href="/terms/#refund">Пользовательского соглашения</a>.</p></div>"""
    return page("/tariffs/", "Тарифы и оплата", body, f"Тарифы {NAME}: сроки, цены и порядок оплаты.")


def terms() -> str:
    body = f"""<div class="doc"><h1>Пользовательское соглашение</h1><p class="updated">Редакция от {UPDATED}</p>
<h2>1. Общие положения</h2>
<p>1.1. Настоящее Пользовательское соглашение (далее — «Соглашение») регулирует порядок использования онлайн-сервиса
«{NAME}»: Telegram-бота <a href="{BOT_LINK}">@{BOT}</a> и сайта <a href="{SITE}">{SITE.replace("https://", "")}</a>
(далее — «Сервис»), предоставляемого Администрацией.</p>
<p>1.2. Используя Сервис, включая запуск бота, получение пробного доступа, оплату услуг или подключение устройства,
Пользователь подтверждает, что полностью ознакомился с условиями Соглашения и принимает их в полном объёме.</p>
<p>1.3. В случае несогласия с условиями Соглашения Пользователь обязан прекратить использование Сервиса.</p>
<h2>2. Характер услуги</h2>
<p>2.1. Сервис предоставляет услугу нематериального характера — доступ к защищённому сетевому соединению (VPN) через
серверы Сервиса на оплаченный срок (далее — «Подписка»).</p>
<p>2.2. Доступ выдаётся в виде ссылки-подписки для приложения-клиента (Happ) на iPhone, iPad, Android, Windows и macOS.
Подписка действует на устройствах в пределах лимита тарифа (до {DEVICES} устройств).</p>
<p>2.3. Новым пользователям может предоставляться бесплатный пробный период — {TRIAL["days"]}, до {TRIAL["devices"]}
устройств и {TRIAL["gb"]} ГБ трафика, один раз на аккаунт Telegram.</p>
<p>2.4. Администрация вправе заменять серверы и маршруты, сохраняя работоспособность услуги.</p>
<h2>3. Отказ от гарантий и ответственности</h2>
<p>3.1. Сервис предоставляется на условиях «как есть».</p>
<p>3.2. Администрация не гарантирует соответствие Сервиса ожиданиям Пользователя, доступность сайтов и сервисов третьих
лиц, а также бесперебойную работу Сервиса, в том числе при ограничениях со стороны операторов связи.</p>
<p>3.3. Администрация не несёт ответственности за прямые или косвенные убытки, действия третьих лиц, временные
технические сбои и неисправность устройства Пользователя.</p>
<p>3.4. Ответственность Администрации ограничена стоимостью оплаченной Подписки за текущий период.</p>
<h2>4. Законность использования</h2>
<p>4.1. Сервис не предназначен для поощрения, организации или содействия противоправной деятельности.</p>
<p>4.2. Пользователь обязуется использовать Сервис исключительно в рамках применимого законодательства.</p>
<p>4.3. Ответственность за законность использования Сервиса полностью возлагается на Пользователя.</p>
<h2>5. Использование доступа</h2>
<p>5.1. Подписка предназначена для личного использования. Запрещается перепродавать доступ, передавать ссылку-подписку
третьим лицам сверх лимита устройств, использовать Сервис для рассылок, атак и сканирования сетей.</p>
<h2>6. Ограничение доступа</h2>
<p>6.1. Администрация вправе приостановить или ограничить доступ при нарушении Соглашения, выявлении злоупотреблений,
требованиях законодательства или платёжных провайдеров. Ограничение не освобождает Пользователя от обязательств,
возникших ранее.</p>
<h2 id="refund">7. Платежи и возвраты</h2>
<p>7.1. Оплата производится на условиях, указанных в Сервисе до момента оплаты; актуальные цены — на странице
<a href="/tariffs/">«Тарифы и оплата»</a>. Оплата разовая, автоматических списаний нет.</p>
<p>7.2. В связи с нематериальным характером услуги возврат после предоставления доступа не осуществляется, за исключением
случаев, когда услуга не была оказана по технической вине Сервиса или доступ фактически не был предоставлен.</p>
<p>7.3. Для рассмотрения возврата Пользователь обращается в <a href="/support/">поддержку</a> в течение 24 часов с
момента оплаты, указав дату и сумму платежа. Решение принимается Администрацией индивидуально.</p>
<p>7.4. Пользователь обязуется не инициировать возврат платежа (chargeback) без предварительного обращения в поддержку.</p>
<h2>8. Конфиденциальность</h2>
<p>8.1. Обработка данных — по <a href="/privacy/">Политике конфиденциальности</a>.</p>
<h2>9. Изменение условий</h2>
<p>9.1. Администрация вправе изменять Соглашение; актуальная версия публикуется на этой странице и доступна по кнопке
«Документы» в боте. Продолжение использования Сервиса означает согласие с обновлёнными условиями.</p>
<h2>10. Контакты</h2><p>10.1. Поддержка: {contact_line()}. Срок ответа — до {REPLY_HOURS} часов.</p>
<p class="note">Используя Сервис (в том числе запуская бота и/или вводя команду /start), Пользователь подтверждает, что
ознакомлен с Соглашением и принимает его условия в полном объёме.</p></div>"""
    return page("/terms/", "Пользовательское соглашение", body, f"Условия использования {NAME}, оплаты и возврата.")


def privacy() -> str:
    body = f"""<div class="doc"><h1>Политика конфиденциальности</h1><p class="updated">Редакция от {UPDATED}</p>
<h2>1. Общие положения</h2>
<p>1.1. Политика регулирует обработку и защиту информации, которую Пользователь передаёт при использовании сервиса
«{NAME}»: Telegram-бота <a href="{BOT_LINK}">@{BOT}</a> и сайта <a href="{SITE}">{SITE.replace("https://", "")}</a>.</p>
<p>1.2. Используя Сервис, Пользователь соглашается с Политикой; при несогласии — прекращает использование Сервиса.</p>
<h2>2. Какие данные мы получаем</h2><ul><li>идентификаторы аккаунта Telegram: ID, имя и никнейм;</li>
<li>техническую информацию: IP-адрес, тип устройства и приложения — для работы подключения и учёта устройств;</li>
<li>сведения о доступе: тариф, срок подписки, объём трафика;</li><li>историю обращений в поддержку.</li></ul>
<p>Сервис не требует паспортных данных и документов, не просматривает и не сохраняет содержимое передаваемых данных.
Данные банковских карт вводятся на стороне платёжного сервиса — Сервис их не получает и не хранит.</p>
<h2>3. Зачем</h2><ul><li>выдача и продление доступа, учёт устройств и трафика;</li>
<li>связь с Пользователем, уведомления и ответы поддержки;</li><li>анализ и улучшение работы Сервиса.</li></ul>
<h2>4. Передача третьим лицам</h2><p>Данные не передаются третьим лицам, кроме случаев, предусмотренных законом,
необходимых для исполнения обязательств (например, при работе с платёжными системами) или с согласия Пользователя.</p>
<h2>5. Хранение и защита</h2><p>Данные хранятся в течение срока, необходимого для целей обработки. Пользователь может
запросить удаление своих данных через <a href="/support/">поддержку</a>. Администрация принимает разумные меры защиты, но
не гарантирует абсолютную безопасность передачи данных через интернет.</p>
<h2>6. Изменения</h2><p>Администрация вправе изменять Политику; продолжение использования Сервиса означает согласие с
новой редакцией.</p>
<h2>7. Контакты</h2><p class="note">По вопросам обработки данных: {contact_line()}.</p></div>"""
    return page("/privacy/", "Политика конфиденциальности", body, f"Как {NAME} обрабатывает и защищает данные.")


def support() -> str:
    email = (f'<p>Почта: <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a></p>' if SUPPORT_EMAIL else "")
    body = f"""<div class="doc"><h1>Поддержка</h1><p>Отвечаем на вопросы о подключении, оплате и возврате.
Обращение — прямо в Telegram-боте, ответ придёт туда же.</p>
<h2>Как написать</h2><ul><li>откройте бота <a href="{SUPPORT_LINK}">@{BOT}</a> и нажмите «💬 Поддержка»;</li>
<li>опишите вопрос, можно приложить скриншот;</li><li>сообщение получит администрация сервиса, ответ придёт в этот же чат.</li></ul>
<div class="actions"><a class="btn" href="{SUPPORT_LINK}" target="_blank" rel="noopener noreferrer">Написать в поддержку</a></div>
{email}<h2>Срок ответа</h2><p class="note">Обычно — в течение нескольких часов, не позднее {REPLY_HOURS} часов.</p>
<h2>Что указать</h2><ul><li>устройство и приложение, где не работает подключение;</li>
<li>по оплате и возврату — дату, сумму и способ оплаты;</li><li>скриншот ошибки, если он есть.</li></ul></div>"""
    return page("/support/", "Поддержка", body, f"Контакты поддержки {NAME}.")


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    for path, render in (("", home), ("tariffs", tariffs), ("terms", terms), ("privacy", privacy), ("support", support)):
        folder = os.path.join(OUT, path)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(render())
    with open(os.path.join(OUT, "style.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS.strip() + "\n")
    with open(os.path.join(OUT, "icon.svg"), "w", encoding="utf-8") as fh:
        fh.write(LOGO.replace(' class="logo__mark"', ' xmlns="http://www.w3.org/2000/svg"').replace(' aria-hidden="true"', ""))
    with open(os.path.join(OUT, "404.html"), "w", encoding="utf-8") as fh:
        fh.write(page("/404", "Страница не найдена", '<div class="doc"><h1>Страница не найдена</h1>'
                      '<p><a href="/">На главную</a></p></div>', NAME))
    print("готово:", OUT)


if __name__ == "__main__":
    main()

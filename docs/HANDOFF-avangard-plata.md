# Передача работы: заказные боты Avangard VPN и Plata VPN (и что было с Etalon)

Документ для продолжения работы в другом аккаунте Claude. Состояние на 15.10.2026 ~22:00 МСК.
Секретов здесь нет — только пути к файлам, где они лежат.

## 0. Правила владельца (соблюдать обязательно)

- Отвечать **только по-русски**.
- **Коммитить, но никогда не пушить** — владелец пушит сам.
- Команды для владельца — чистыми блоками, без `#`-комментариев внутри.
- Пароли, присланные в чат, **не использовать** (вход только по SSH-ключам); секреты не печатать на экран,
  передавать через файлы/stdin.
- Ответы клиентам в поддержку — только практичные шаги, без «пришлите скрин test-ipv6» и прочей диагностики.
- «Ничего не сломай»: перед выкладкой файла — `diff` серверной копии с локальной; правки env — через
  временный файл и `mv`, никогда `cat > живой_файл`; после рестарта смотреть `is-active` **и** время жизни процесса.
- Git-хук `block-no-verify` блокирует любую команду, где рядом с `git commit` есть `-n`/`--no-…`
  (даже `pytest --no-cov`). Коммит — отдельной командой.
- Mac владельца обычно на нашем VPN → исходящий 22 порт режется. На серверы ходить через VK-прыжок
  `ubuntu@212.233.122.241` (ключ `~/.ssh/vkcloud`). Бот-сервер троттлит частые SSH — одно соединение
  с ControlMaster, без пачек параллельных подключений.
- Не на основном аккаунте владелец просил **не запускать localhost** — только тесты/сборка/коммиты.

SSH-конфиг, которым пользовался (скопировать к себе, пути ключей те же):

```
Host *
  BatchMode yes
  ControlMaster auto
  ControlPath ~/.ssh/cm-%C
  ControlPersist 900
Host vk
  HostName 212.233.122.241
  User ubuntu
  IdentityFile ~/.ssh/vkcloud
Host botus
  HostName 23.95.3.18
  User root
  IdentityFile ~/.ssh/vpnbot_vps
  ProxyJump vk
```

## 1. Что это за проект

Основной продукт — **UnLock VPN**: Telegram-бот (aiogram, `/opt/vpn-bot`, служба `unlock-vpnbot`),
панель **Marzban** (одна на все наши серверы-выходы PL/NL/DE/FI/US/LT…), **шлюз подписок**
`unlock-subgw` (`services/sub_gateway.py`, на сервере работает КОПИЯ `/opt/sub_gateway.py` + `/opt/xray_json.py`,
настройки `/etc/unlock-subgw.env`), сайт unlockproject.site (168.113.210.6), VK Cloud 212.233.122.241 —
фронт подписок, мост и SSH-прыжок.

Репозиторий: `~/vpn-bot-multisub` (ветка `feature/multi-subscriptions`, выровнена с прод-сервером; в ней вся
работа по заказным ботам). `~/vpn-bot` — старая рабочая копия (сайт основного проекта выкладывать только оттуда).

**Заказные (white-label) боты** — один общий код `marat_bot/` (Bot API напрямую через `marat_bot/tg.py`,
без aiogram: ~36 МБ на процесс; aiogram на бот-сервере = ~420 МБ, памяти мало). Каждый бот — отдельная
systemd-служба с тем же кодом `/opt/vpn-bot/marat_bot` и своим env (`MARAT_*`):

| Бот | Служба | env | Префикс учёток | Тема | Адрес подписок |
|---|---|---|---|---|---|
| Avangard VPN | `avangard-vpnbot` | `/etc/avangard-bot.env` | `corp_avg_` | `avangard` (5 языков) | `https://a.212.233.122.241.sslip.io` |
| Plata VPN (@plataavpn_bot) | `yaroslav-vpnbot` | `/etc/yaroslav-bot.env` | `corp_yar_` | `plata` | `https://y.212.233.122.241.sslip.io` |
| Etalon VPN (@etallonvpn_bot) | — у нас **выключен** | — | `corp_mrt_` | `etalon` | переехал к заказчику, см. §5 |

Как устроено:
- Пользователь получает пробник (3 дня, 10 ГБ, 2 устройства) — учётка панели `<префикс><telegram id>`.
- Шлюз по шаблонам `corp_xxx_*` в `/etc/unlock-subgw.env` отдаёт подписку под названием бота, без следов
  UnLock: `SUB_TITLES`, `UNBRANDED_USERS`, `COMPACT_USERS`, `MANUAL_DEVICE_LIMITS`, `USER_SHARED_CORP_HOSTS`,
  `SUB_BASES`, `AUTO_TITLES`, `PICKER_USERS` и т. п.
- Адреса `a.`/`y.212.233.122.241.sslip.io` — nginx на VK (`/etc/nginx/sites-available/avangard-front`,
  `yaroslav-front`) → шлюз. Имя `212.233.122.241.sslip.io` без приставки занято маскировкой релея — не трогать.
- Меню бота: пробник, Подключить, Моя подписка, Тарифы → оплата (**заглушка**, цены `MARAT_PLANS`,
  по умолчанию 199/549/999/1799), Пригласить, Промокод, Отзыв, Помощь, Поддержка, «📄 Документы»
  (если задан `MARAT_SITE_URL`).
- Поддержка (`marat_bot/support.py`): сообщения пользователя копируются админам из `MARAT_ADMINS`
  (ники и/или ID); админ отвечает реплаем. **Пока `MARAT_ADMINS` пуст — поддержка показывает заглушку.**
  Ник привязывается к ID, когда админ первый раз пишет боту.
- Админ-команды: `/admin`, `/users`, `/user ID`, `/extend ID ДНИ`, `/traffic ID ГБ` (только свои учётки).
- Тексты/баннеры — `marat_bot/themes/<тема>.py` + `themes/assets/<тема>/`, генераторы `scripts/make_*_banners.py`.
  Тест `test_branded_bots_never_advertise_bypassing_blocks` держит «мягкие» тексты для платёжных систем.
- Выкладка кода ботов: rsync `marat_bot/` → `/opt/vpn-bot/marat_bot` (сначала diff!), затем
  `systemctl restart avangard-vpnbot yaroslav-vpnbot`; бэкапы в `/root/deploy-backups/`.

Сайты заказчиков — Next.js статикой, на сервере сайта 168.113.210.6 (`/var/www/<имя>`, nginx с LE webroot):

| Сайт | Исходник | Адрес | nginx |
|---|---|---|---|
| Avangard | `sites/avangard-web` | https://avangard.168.113.210.6.sslip.io | `deploy/avangard-site/avangard.conf` |
| Plata | `sites/plata-web` | https://plata.168.113.210.6.sslip.io | `deploy/plata-site/plata.conf` |
| Etalon | `sites/etalon-web` | getetalon.site (переезжает к заказчику) | — |

Сборка: `npm run build` в папке сайта → `out/` → rsync в `/var/www/<имя>/`. Старый генератор
`scripts/make_plata_site.py` **не запускать** — затрёт `out/` полноценного сайта.

## 2. Avangard VPN — состояние и что осталось

Сделано (коммиты b6e05d6, 96b2120, 9b3d7f7, 1dbbe4a, b6d10dc, 132b4cf):
- Бренд «Замок» (тёмно-зелёный #0B231B + античное золото #B08A3E, башня со скважиной, Comfortaa прописными),
  баннеры на 5 языках (ru/en/uk/zh/fa; фарси рисует `scripts/render_text.swift`).
- Выбор языка при первом /start, `/language`, «🌐 Язык» в меню, «🌐 Сменить язык» под подтверждением.
- Имя «Avangard VPN», аватар поставлен через Bot API `setMyProfilePhoto` (картинку описания — только BotFather).
- Серверы как в тест-ссылке `exp_denl_7d`: 🇩🇪 + 🇳🇱 через VK-мост + «⚡️ Авто-выбор», без режима РУ
  (`FOREIGN_ONLY_USERS` и `FOREIGN_VIA_VK_USERS` с `corp_avg_*` в env шлюза).
- Сайт https://avangard.168.113.210.6.sslip.io (скважина раскрывается один раз по IntersectionObserver —
  тяжёлые сцены к scroll не привязывать).

Осталось / ждём от заказчика:
1. **Ник админа** → `MARAT_ADMINS=` в `/etc/avangard-bot.env`, рестарт `avangard-vpnbot` (иначе поддержка — заглушка).
2. **`MARAT_SITE_URL`** в env не задан → кнопки «📄 Документы» нет. Задать адрес сайта (или его домен,
   когда купят) и перезапустить.
3. Свой домен для сайта (сейчас sslip) — по образцу getetalon.site (A-записи → сервер, certbot webroot, vhost).
4. Оплата — заглушка в боте и на сайте. Подключать, когда заказчик даст ключи платёжки.
5. Токен бота светился в чате → заказчику перевыпустить (`/revoke` в BotFather), вписать в env.
6. ⚠️ Трафик через VK-мост идёт по общим ключам full-de/full-nl → лимит пробника 10 ГБ фактически не считается.
7. Если заказчик захочет уехать на свои серверы — рецепт ровно как у Etalon (§5, `deploy/etalon-stack/`).
   Ключ для его серверов уже есть: `~/.ssh/avangard` (pub отдан владельцу 13.10). План — `deploy/avangard/README.md`.

## 3. Plata VPN (бывший «Ярослав VPN») — состояние и что осталось

Сделано (коммиты 6779f97, b369b82, 39865b1, 878e3b2):
- Тема `plata` (кремовый #FEF8EC, тёмно-синий щит #172854, янтарный шеврон), баннеры.
- Бот @plataavpn_bot (служба та же `yaroslav-vpnbot`); старый @yaroslavtestvpn_bot не обслуживается.
- Серверы как у Etalon: PL / FI-2 / NL / US + Авто + Режим РУ-сервисов.
- Сайт https://plata.168.113.210.6.sslip.io («щит и шевроны»), документы `/tariffs/ /terms/ /privacy/ /support/`,
  `/checkout/?plan=` — форма (срок, e-mail, согласие) с заглушкой оплаты «Скоро».
  `MARAT_SITE_URL` в боте задан → «📄 Документы» работает.

Осталось / ждём от заказчика (Ярослав):
1. **ЮKassa**: ждём `shopId` + секретный ключ. Ярославу уже объяснено, как выдать доступ; **ключ после
   подключения НЕ удалять** (без него бот не сможет создавать платежи и проверять их). Дальше: оплата в боте
   (по образцу нашей ЮKassa в основном проекте — `services/billing_api.py`, чеки, вебхук) и на сайте
   (статике нужен бэкенд для создания платежа — переиспользовать наш API или маленький сервис рядом с ботом).
2. **Реквизиты** (ФИО / статус / ИНН / e-mail поддержки) в документах сайта — пока их нет.
3. **Ник админа** → `MARAT_ADMINS` в `/etc/yaroslav-bot.env` (поддержка сейчас заглушка).
4. Токены (старый и новый) светились в чате → перевыпустить.
5. Свой домен для сайта (сейчас sslip).

## 4. Основной проект — что сделано сегодня (15.10)

- **Лимит устройств у второй подписки** (коммит 2303491, выложено в `/opt/sub_gateway.py`):
  `_token_username` не узнавал `tg_<id>_s2` и читал укороченный префикс токена как основную подписку
  → все доп. подписки делили пул устройств основной. Регулярка теперь `tg_-?\d{1,20}(?:_s\d{1,2})?`, тесты есть.
  Повод — обращение пользователя 8984740385 (основная 5/5 устройств, вторая показывала «лимит»).
  Бэкап: `/root/deploy-backups/subgw-s2-vk-20261015/`.
- **«✅ РУ сервисы» без «· VK»** в названиях (тот же коммит).
- **VK-мост в Авто до конца понедельника**: `AUTO_BRIDGE_USERS=exp_ruvk_1,tg_*` в `/etc/unlock-subgw.env`;
  `bridge-revert.timer` (бот-сервер) сам выключит в **00:00 МСК 20.10.2026** (скрипт `/root/diag/bridge-revert.sh`,
  журнал `/root/diag/bridge-revert.log`). `VK_RELAY_USERS=exp_ruvk_1,tg_*` (РУ-режим через VK) стоит без срока.
- `/stats` открыт @edismee через `STATS_VIEWERS` (коммит 5f67a03).
- corp_unl_trial продлена до 22.10 23:59 МСК.

## 5. Etalon VPN — передан заказчику (Марат)

Всё работает на его 4 серверах 4vps.su, с нами не связано. Подробности — `deploy/etalon-stack/README.md`
и гайд для Марата: https://claude.ai/artifact/6bkgCrqsSNexfA4syT4qb2 (исходник — scratchpad сессии, копия
не нужна: гайд опубликован). Доступы к панели — `~/Desktop/Etalon-Marzban.txt`. Ключ к его серверам —
`~/.ssh/etalon_ed25519` (Марат должен заменить на свой).

Схема: вход Москва 89.221.203.114 (marzban-node, VLESS Reality 443/2053/2083, nginx за Reality: сайт,
подписки, панель) → Hysteria2 UDP 50000 → выходы NL 147.45.50.226 (главный: Marzban, бот, шлюз
`deploy/etalon-stack/etalon_gateway.py`), FR 147.45.50.237, DE 77.110.107.198 (через NL). Причина: ТСПУ режет
TCP из РФ к NL/DE, AmneziaWG душится. SSH к NL из РФ — через Москву `127.0.0.1:2201`.

Осталось:
1. Владелец меняет A-записи getetalon.site (`@`, `www`) в reg.ru на 89.221.203.114 → certbot + vhost
   (скрипт был `etalon_site_finish.sh` в scratchpad; если его нет — сделать вручную по образцу: certbot webroot
   `/var/www/letsencrypt`, vhost на `127.0.0.1:9443` в `/etc/nginx/sites-available/etalon-tls`, `nginx -t` → reload).
2. Два активных пробника (до 17.10) ещё на наших старых ссылках — владелец решает: написать им или дать истечь.
3. **Чистка у нас после 17.10 и переключения DNS**: учётки `corp_mrt_*` в нашей панели; строки `corp_mrt_*`
   в `/etc/unlock-subgw.env` (+ restart unlock-subgw); маршрут `/mapp/etalon*` в Caddy; VK `marat-front`;
   сайты etalon/getetalon на 168.113.210.6; служба/env `marat-vpnbot` (бэкап уже есть:
   `/root/deploy-backups/etalon-handover-20261015-180420`). ⚠️ `corp_mrt_*` стоит в тех же строках env, что
   `corp_yar_*` и `corp_avg_*` — удалять аккуратно, только свои элементы списка.
4. Уточнить у 4vps, что «Франция» правда во Франции (геобазы показывают Амстердам).

## 6. Где что лежит

- Память Claude (контекст по всем проектам): `~/.claude/projects/-Users-egoordd/memory/` — индекс `MEMORY.md`;
  по этим ботам: `project_avangard_bot.md`, `project_yaroslav_bot.md`, `project_marat_bot.md`,
  `project_etalon_handover.md`, `project_etalon_site.md`, `project_bot_vps_memory.md`.
  Другой аккаунт эту папку видит, если работает на этом же Mac под тем же пользователем.
- Токены ботов: `~/.config/unlock/avangard_bot_token` (600); остальные — только в env на сервере.
- Ключи: `~/.ssh/vpnbot_vps` (бот-сервер), `~/.ssh/vkcloud` (VK), `~/.ssh/avangard`, `~/.ssh/etalon_ed25519`.
- Тесты: `../vpn-bot/.venv/bin/python -m pytest tests/ -q` (venv основной копии; в worktree своего нет).
  Для заказных ботов: `tests/test_marat_bot.py`, `tests/test_marat_webapp.py`, шлюз — `tests/test_sub_gateway.py`, Etalon — `tests/test_etalon_gateway.py`.

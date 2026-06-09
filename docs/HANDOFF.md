# VPN-bot — HANDOFF (передача в новый чат)

> Назначение: за 10 минут понять, что это за проект, что уже работает, какая инфраструктура живая, что сделано в коде и какой следующий шаг.
> Дата: 2026-06-10. Репозиторий: `~/vpn-bot`.

---

## 0. Главное за сессию (TL;DR)
**Мы наконец починили VPN.** VLESS+Reality «подключается, но интернета нет» на реальном iOS/LTE российского оператора — **решено и проверено на живом телефоне (2026-06-08).** Корень — **SNI↔IP корреляция** оператора; фикс — **own-domain Reality (self-steal)**. Бэкенд боевой, подписка бота отдаёт рабочий конфиг. Подробности — `docs/WORKING_VPN_CONFIG.md`.

Следующий шаг — **реальный e2e самого бота** против живого Marzban (см. §7).

---

## 1. Идея продукта
Telegram-бот (+ сайт + позже приложение), продающий подписки на VPN, устойчивый к DPI операторов/РКН. Тарифы по плотности: Общий → Индивидуальный (≤N на ноду) → Выделенный. Конфиг отдаётся **ссылкой-подпиской** (авто-обновление). Серверы под спрос (автоскейл). Оплата возможна вне Telegram (сайт).
Полное описание: `docs/PRODUCT_ARCHITECTURE.md`. План по фазам: `docs/IMPLEMENTATION_PLAN.md`.

## 2. Зафиксированные решения
- **Панель:** код поддерживает обе — `PANEL_PROVIDER=remnawave|marzban`. **Текущий боевой baseline — Marzban 0.8.4.** Remnawave — целевая альтернатива.
- **Протокол ядра:** VLESS+Reality (own-domain self-steal). Запасной — Hysteria2.
- **Облако автоскейла:** Vultr (позже). **Сайт:** Next.js. **AmneziaWG** — легаси (выведен из ядра).
- **Рабочий процесс:** обычно «Claude планирует — Codex кодит», пуш делает пользователь вручную (только его ключ на GitHub). НО в этой сессии пользователь явно разрешил Claude менять код и сервер напрямую для починки VPN.

## 3. ЖИВАЯ ИНФРАСТРУКТУРА
- **Сервер:** Cloudzy, Utah, **`144.172.101.217`**, Ubuntu 24.04, **0.5 ГБ RAM** (впритык!) + 1 ГБ swap. IPv6 отключён.
- **SSH:** `ssh root@144.172.101.217` (ключ `~/.ssh/id_ed25519`, парольная фраза). Если `Permission denied` и `ssh-add -l` пуст → выполнить `ssh-add --apple-load-keychain` (подтянет ключ из macOS keychain).
- **Marzban 0.8.4** в docker (`marzban-marzban-1`), конфиг `/var/lib/marzban/`, БД `db.sqlite3`. Панель: nginx `80/tcp`; подписки HTTPS `8443/tcp` через `144.172.101.217.sslip.io` (есть **реальный Let's Encrypt** серт).
- **Xray inbounds:** `VLESS Reality` на `443/tcp`, `Shadowsocks` на `1080`.
- **Hysteria2** (standalone) на `443/udp`, self-signed, пароль в `/etc/hysteria/config.yaml`. Server-side проверен.
- **Бэкап рабочего конфига:** `/root/working-reality-backup/` (xray_config, db, WORKING_PARAMS.txt).

## 4. РАБОЧИЙ Reality-конфиг (закреплён)
```
address == serverName(SNI) : 144.172.101.217.sslip.io   (резолвится в наш IP!)
dest (self-steal)          : 144.172.101.217:8443        (локальный nginx, реальный LE серт, TLS1.3)
fingerprint                : firefox
flow                       : xtls-rprx-vision
publicKey                  : XfIFLXO4LUizIpiNXay1p8HL_ou5thasFS5bPusNziw
shortId                    : 3684c6d01d7363a4
```
**Marzban Host** (db.sqlite3, inbound_tag `VLESS Reality 443`) обновлён: `address`/`sni`=sslip-домен, `fingerprint`=firefox. Подписка бота (`/sub/{token}/v2ray-json`, UA Happ) проверена — отдаёт эти параметры.

**Корень проблемы:** оператор делал SNI↔IP корреляцию — SNI `www.microsoft.com` на наш не-MS IP палился как прокси и душился. **Никогда не использовать чужой SNI на нашем IP.** Серверный smoke это НЕ ловит — единственная приёмка — реальный телефон по LTE.

## 5. Состояние кода (репозиторий ~/vpn-bot)
- **Фаза 1 (MVP)** — реализована на коде+моках: Alembic+миграции, модели (User/Subscription/Plan/Node), `services/panel_gateway.py` (абстракция **Marzban + Remnawave**!), `services/marzban_client.py`, `services/panel_client.py` (Remnawave), `services/subscription.py`, `services/tariffs.py`, хэндлеры (start/cabinet/buy/connect_device/locations), CryptoBot, scheduler (poll/traffic_sync/expiring).
- **Фаза 2** — на коде+моках: `services/autoscaler.py` (Vultr + node/Host provisioning), capacity-логика, UX локаций, autoscale_check. **Vultr вживую не проверен.**
- **Фаза 3** — начат `services/billing_api.py` (базовый слой; сайта ещё нет).
- **Тесты:** ~152 pytest, ~92% покрытия (моки). Запуск: `cd ~/vpn-bot && . .venv/bin/activate && pytest`.
- **Probe-скрипты:** `scripts/marzban_contract_probe.py`, `remnawave_contract_probe.py`, `vultr_contract_probe.py`, `live_autoscaler_probe.py`, `register_static_node.py`, `reality_smoketest.sh`, `hysteria2_smoketest.sh`, `build_client_profile.py`.

## 6. Git
- Последний коммит: `2b44bd8` (working Reality + Phase 1/2). **3 коммита впереди origin, НЕ запушены** — пушит пользователь вручную.
- `.env` в gitignore (секреты: BOT_TOKEN, CRYPTOBOT_TOKEN, креды панели). `.env.example` актуален (есть `PANEL_PROVIDER`, Marzban/Remnawave блоки).

## 7. СЛЕДУЮЩИЙ ШАГ — реальный e2e бота (пункт 24 плана)
Бэкенд работает; теперь прогнать сам бот против живого Marzban:
`/start → бот создаёт юзера в Marzban → выдаёт sub-ссылку → импорт в Happ → интернет на телефоне; покупка → продление.`

Нужно:
1. `.env`: `PANEL_PROVIDER=marzban`, `MARZBAN_API_URL=https://144.172.101.217.sslip.io:8443`, **админ-креды Marzban** (достать/сбросить по SSH: `docker exec -it marzban-marzban-1 marzban cli admin ...`), `BOT_TOKEN` (от @BotFather, у пользователя), опц. `CRYPTOBOT_TOKEN`.
2. Где гонять бот: **не на Cloudzy** (0.5 ГБ RAM мало под Marzban+Xray+Hysteria+bot+postgres+redis). Локально на Mac (Docker) или отдельный мелкий сервер.
3. Поднять docker-compose (bot+postgres+redis), миграции, прогнать e2e.

Открытые хвосты: Vultr-автоскейл live-проверка (платно); сайт (Фаза 3); привести `services/client_profiles.py` в порядок (там был over-engineered balancer/burstObservatory — для подписки Marzban не используется, но мусор).

## 8. Ключевые уроки (важно для нового чата)
- **«Серверный smoke прошёл» ≠ «работает на телефоне».** Попадались 3+ раза. Единственная приёмка VPN — реальный iOS/LTE.
- **Reality «connects but no internet» на RU = SNI↔IP корреляция** → own-domain SNI, резолвящийся в IP ноды (sslip.io бесплатно) + firefox fp + реальный серт на dest.
- **Не винить телефон/оператор как отмазку** — продукт обязан переживать DPI by design.
- Сравнивать наш конфиг с **рабочим конкурентом** (SaveVPN) поле-в-поле: `docs/examples/saveworking_nl_reality.json` (VLESS Reality), `saveworking_us_hysteria.json` (Hysteria2).
- Пуши — только пользователь. Команды в блоках — чистые, без inline-комментариев.

## 9. Связанные документы
- `docs/PRODUCT_ARCHITECTURE.md` — идея и финальная архитектура.
- `docs/IMPLEMENTATION_PLAN.md` — поэтапный план + «Текущая точка».
- `docs/WORKING_VPN_CONFIG.md` — рабочая Reality-конфигурация, корень и фикс.
- `docs/PHASE0_RUNBOOK.md`, `docs/LIVE_VERIFICATION.md` — деплой панели/ноды и live-гейты.
- `docs/PROJECT_CONTEXT.md` — ранняя история (WireGuard/AmneziaWG эра).
- `~/Desktop/VPN_проблемы_и_решения.md` — разбор обеих прошлых VPN-проблем.

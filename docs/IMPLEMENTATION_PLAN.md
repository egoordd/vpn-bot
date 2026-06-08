# VPN-bot — План реализации

> Поэтапный план постройки продукта, описанного в `PRODUCT_ARCHITECTURE.md`.
> Последнее обновление: 2026-06-04.

## Зафиксированные решения
- **Панель:** **Remnawave** (современная, встроенный лимит устройств по HWID, модульная мульти-нода, REST API). *(Изначально рассматривали Marzban; переключились на Remnawave.)*
- **Облако для автоскейла:** Vultr (25+ регионов, API, почасовой биллинг). Hetzner/Aeza — позже для удешевления/RU.
- **Сайт:** Next.js + общий биллинг-API.
- **AmneziaWG:** выводится из ядра, провижининг переезжает на панель (Xray VLESS+Reality). Старый код — легаси-референс.

Обозначения: **[ops]** — пользователь на сервере · **[Codex]** — код · **[Claude]** — план/спека/верификация · пуш — всегда пользователь вручную.

---

## ФАЗА 0 — Бэкенд-фундамент (без бота)
Цель: поднять панель+ноду и подтвердить реальный мобильный браузинг. VLESS+Reality остаётся основным кандидатом, но Phase 0 считается закрытой только после рабочего e2e на реальном iOS/LTE; если Reality не проходит, нужен ранний fallback на Hysteria2/Shadowsocks.

1. **[ops]** Сервер под панель (Ubuntu 24.04, ≥2 ГБ RAM, 2 ядра, 20 ГБ, публичный IP). Не эфемерный.
2. **[ops]** Домен для production (HTTPS, страница подписки, reverse-proxy). Для Phase 0 smoke допустим временный HTTPS tunnel.
3. **[Claude/ops]** Дымовой тест: голый Xray + VLESS+Reality на 1 сервере → проверить обход DPI на мобильном (домен не нужен). *(Live-факт: серверный и внешний Mac smoke проходят, но реальный iOS/LTE клиент шлёт Reality ClientHello, который Xray не принимает до конца; Reality не закрывает Phase 0.)*
4. **[ops/Claude]** Установить **Remnawave** (docker), reverse-proxy + SSL, страница подписки, sudo-админ.
5. **[ops]** Поднять первую **ноду** (Remnawave-node + Xray), привязать к панели, настроить inbound и Host. Для старта допустим single-server: panel и node на одном VPS, Host address = публичный IP этого VPS.
6. **[Claude/ops]** Ранний fallback: поднять Hysteria2 на той же ноде (`8443/udp` для текущего Aeza smoke; `443/udp` только если провайдер пропускает порт) и проверить Happ/Hiddify на реальном iOS/LTE. UDP-порт не конфликтует с Remnawave/Xray на `443/tcp`.
7. **[Claude/ops] Acceptance:** создать тест-юзера/профиль → sub-ссылка или JSON → импорт в клиент → браузинг на мобильном. Бэкенд валиден → идём в бота.

---

## ФАЗА 1 — MVP: бот на панели (общий тариф)
Цель: бот продаёт «Общий» тариф, выдаёт ссылку-подписку, считает трафик/срок, оплата криптой, пробник.

### Схема и миграции
8. **[Codex]** Ввести Alembic.
9. **[Codex]** Модели: `User` (+balance, lang, referrer_id, ref_code), `Subscription` (tier, panel_username, sub_token, traffic/device/expire, status), `Plan` (конфиг тарифов).
10. **[Codex]** Стартовая миграция.

### Клиент панели и биллинг
11. **[Claude]** Спека `services/panel_client.py` (Remnawave API): create_user, get_user, modify_user (продлить/сброс), delete_user, get_usage, sub-link.
12. **[Codex]** Реализация `panel_client` + юнит-тесты (мок HTTP).
13. **[Codex]** `services/subscription.py`: activate(tier, duration) → панель create/modify, сохранить sub_token, выставить срок/трафик/устройства по Plan.
14. **[Codex]** Конфиг тарифов: trial (10ГБ/N дней), standard 1/3/6/12 мес (цены, трафик, устройства).

### Хэндлеры / UX
15. **[Codex]** `start.py` — /start: создать юзера, авто-пробник, кабинет.
16. **[Codex]** `cabinet.py` — профиль, «Моя подписка» (трафик X/Y из панели, срок, sub-ссылка).
17. **[Codex]** `tariffs.py`/`buy.py` — выбор «Общий» → срок → оплата.
18. **[Codex]** `connect_device.py` — sub-ссылка + QR + диплинки приложений (V2RayTun/Streisand/Hiddify) + инструкции.
19. **[Codex]** Клавиатуры.

### Платежи и фон
20. **[Codex]** CryptoBot: инвойс → при оплате activate/extend через панель.
21. **[Codex]** Scheduler: poll_payments, traffic_sync (расход из панели → кабинет, отключение при превышении), check_expiring/deactivate_expired.

### Тесты и деплой
22. **[Codex]** Тесты на panel_client, subscription, хэндлеры, scheduler. Держим 80%+.
23. **[Claude/Codex]** docker-compose (bot+postgres+redis; панель — отдельно), .env (URL панели, токены, домены).
24. **[Claude] Верификация MVP:** pytest + ручной e2e (/start → пробник → импорт → браузинг; покупка → продление).

**MVP готов = можно продавать общий тариф.**

---

## ФАЗА 2 — Премиум-тариф + автоскейлер + локации
25. **[Codex]** Модель `Server/Node` (tier, capacity, region, provider, ip, panel_node_id, current_users, static_ips[]).
26. **[Claude]** Спека `services/autoscaler.py`: Vultr API create/destroy, setup.sh как cloud-init, регистрация ноды в панели.
27. **[Codex]** Реализация автоскейлера + тесты (мок Vultr+панель).
28. **[Codex]** Логика ёмкости: премиум-юзер на ноду count<cap; нет места → поднять; пустая → снести.
29. **[Codex]** UX: выбор/смена локации, флоу премиума «готовим сервер ~2 мин».
30. **[Claude/ops]** setup.sh → cloud-init для ноды + Reality/Hysteria2 fallback.
31. **[Codex]** Scheduler autoscale_check.

---

## ФАЗА 3 — Сайт + карты + рефералка + промокоды
32. **[Codex/Claude]** Выделить общий биллинг-API (бот + сайт).
33. **[Codex]** Сайт Next.js: кабинет, вход (TG Login/email), оплата (карта PSP + крипта), доступен без VPN (чистый домен + зеркала).
34. **[Codex]** Карточный PSP (с учётом РФ).
35. **[Codex]** Реферралка (реф-коды, начисления на баланс, статистика).
36. **[Codex]** Промокоды.
37. **[Codex]** Баланс-кошелёк (пополнение + списание).

---

## ФАЗА 4 — Статичный IP / Dedicated, приложение
38. **[Codex/ops]** Статичный IP: Xray `sendThrough` + мульти-IP ноды (premium-статик) и/или выделенный VPS (dedicated).
39. **[Codex]** Тариф Dedicated (1 юзер = 1 VPS, автоскейл + teardown).
40. **[Codex/ops]** Приложение-клиент (обёртка sing-box) с логином; оплата на сайте.
41. **[Codex/ops]** Мульти-протокольный subscription/JSON генератор: VLESS Reality + Hysteria2 + selector/auto URL-test.

---

## Сквозные задачи
42. Безопасность: секреты панели/облака, аутентификация API, CSRF/throttling сайта.
43. Бэкапы БД (решает «эфемерный сервер убил всех»).
44. Health/мониторинг нод и панели; авто-вывод мёртвой ноды.
45. Тесты ≥80% на каждый новый сервис.

---

## Текущая точка
Кодовая часть **Фазы 1 MVP** почти закрыта: реализованы пункты 8–10, 12–23 и 45. Пункт 24 закрыт только по pytest/мокам и требует обязательного live gate из `LIVE_VERIFICATION.md` на реальной панели/ноде Remnawave.

Начата **Фаза 2**: пункты 25–29 и 31 закрыты на уровне кода и мок-тестов — добавлена модель `Node`, миграция, репозиторные методы, `services/autoscaler.py` для Vultr + Remnawave node/Host provisioning/decommission, single-server manual-node registration, логика назначения/освобождения capacity для premium-нод, UX выбора/смены premium-локации и `Scheduler autoscale_check`. Vultr/cloud-init остаётся mock-verified до платной live-проверки.

Операционная **Фаза 0** перезапущена на месячном VPS `144.172.101.217` с Ubuntu 24.04.3 и Marzban `0.8.4`: добавлен 1 GiB swap, Marzban доступен через Nginx на `80/tcp`, клиентские подписки доступны по HTTPS на `8443/tcp` через `144.172.101.217.sslip.io`, Xray слушает `VLESS Reality 443` на `443/tcp` и дефолтный `Shadowsocks TCP` на `1080/tcp,udp`. `scripts/marzban_contract_probe.py` прошёл живой API gate через внешний `https://144.172.101.217.sslip.io:8443`: `GET /api/system`, `GET /api/inbounds`, `POST/GET/PUT /api/user`. Тестовый пользователь `codex_smoke` продлён на 30 дней с лимитом 10 GiB. Включён Marzban `v2ray-json` для Happ: `/sub/{token}/v2ray-json` и обычный `/sub/{token}` под `Happ/4.10.0` возвращают `application/json` с `UseIPv4` и без `allowInsecure`; `xray run -test` и server-side Xray client smoke через этот JSON проходят. IPv6 на VPS отключён, nginx больше не слушает `[::]:80`. Старые VPS `62.60.156.158` и одноразовый smoke `91.108.240.76` больше не являются актуальной инфраструктурой.

Пункт 41 начат кодом: добавлен `services/client_profiles.py` и `scripts/build_client_profile.py`, которые строят Happ/Xray JSON с VLESS Reality + Hysteria2 + Shadowsocks/Trojan fallback, `burstObservatory` и routing balancer. Также подготовлен Marzban path: `services/marzban_client.py` покрывает OAuth token, system/inbounds, create/get/modify/delete user, нормализует относительный `subscription_url`, а `services/panel_gateway.py` позволяет включать `PANEL_PROVIDER=remnawave|marzban` для trial/payment/traffic sync без переписывания UX. Marzban API path уже live-verified на Aeza; production-ready статус всё ещё требует импорта QR/ссылки в Happ/Hiddify и реального iOS/LTE браузинга на новой ноде.

## Связанные документы
- `PRODUCT_ARCHITECTURE.md` — идея и финальная архитектура.
- `PHASE0_RUNBOOK.md` — пошаговая установка панели, первой ноды и acceptance Phase 0.
- `LIVE_VERIFICATION.md` — обязательный live gate перед продолжением в Фазу 3.
- `MARZBAN_SMOKE.md` — быстрый live path, если новый VPS ставится сразу с Marzban.
- `MULTIPROTOCOL_SUBSCRIPTION.md` — генератор одного Happ/Xray JSON с fallback-протоколами.
- `PROJECT_CONTEXT.md` — история проекта, AmneziaWG, тесты, уроки.
- `scripts/reality_smoketest.sh` — скрипт дымового теста Reality.

# VPN Bot MVP

MVP Telegram-бота для продажи VPN-доступа по подписке через CryptoBot.
Основной провижининг — Remnawave/VLESS subscription-ссылки; AmneziaWG/WireGuard оставлен как legacy fallback.

## Что внутри

- aiogram 3.x
- PostgreSQL + SQLAlchemy async
- Redis FSM storage
- Remnawave API client для VLESS+Reality provisioning
- Marzban API client для smoke/альтернативной панели
- Multiprotocol Happ/Xray profile generator для Reality + Hysteria2 + Shadowsocks/Trojan fallback
- CryptoBot payments
- QR-коды subscription-ссылок
- APScheduler для напоминаний и отключения истекших подписок
- Alembic migrations
- Docker Compose для запуска бота, PostgreSQL и Redis
- Legacy AmneziaWG/WireGuard fallback

## Подготовка Remnawave

До запуска бота панель и первая нода Remnawave должны быть подняты отдельно:

1. Панель Remnawave доступна по HTTPS-домену.
2. В панели создан API-токен для бота.
3. Нода подключена к панели.
4. Создан и проверен inbound VLESS+Reality.
5. Тестовый пользователь из панели импортируется в клиент и реально даёт доступ в интернет.

## Marzban smoke

Если новый VPS устанавливается сразу с Marzban, используйте `docs/MARZBAN_SMOKE.md`. В коде уже есть Marzban API-клиент для создания/чтения/изменения/удаления пользователей, но production-переключение с Remnawave на Marzban должно пройти отдельный live gate.

## Настройка

```bash
cd ~/vpn-bot
cp .env.example .env
```

Заполните `.env`:

- `BOT_TOKEN` - токен бота от `@BotFather`
- `CRYPTOBOT_TOKEN` - токен приложения CryptoBot
- `CRYPTOBOT_API_URL` - URL CryptoBot API, по умолчанию `https://pay.crypt.bot/api`
- `CRYPTOBOT_POLL_INTERVAL` - интервал проверки оплат в секундах
- `PANEL_PROVIDER` - активная панель для провижининга пользователей: `remnawave` или `marzban`
- `REMNAWAVE_API_URL` - URL панели Remnawave, например `https://panel.example.com`
- `REMNAWAVE_API_TOKEN` - API-токен панели Remnawave
- `REMNAWAVE_USERNAME_PREFIX` - префикс username пользователей в панели
- `REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS` - Internal Squad UUIDs для новых/продлеваемых пользователей через запятую
- `REMNAWAVE_NODE_CONFIG_PROFILE_UUID` - config profile для новых autoscaler-нод
- `REMNAWAVE_NODE_INBOUND_UUIDS` - inbound UUID для новых autoscaler-нод через запятую
- `REMNAWAVE_NODE_PORT` - внутренний порт Remnawave Node, обычно `2222`
- `REMNAWAVE_HOST_PORT` - публичный порт inbound/Host для клиентских proxy links, например `1234` в Phase 0
- `REMNAWAVE_HOST_TAG` - tag для Host, которые создает autoscaler
- `REMNAWAVE_STATIC_*` - опциональные значения для регистрации уже существующей single-server node в БД
- `MARZBAN_API_URL`, `MARZBAN_ACCESS_TOKEN` - опциональный доступ к Marzban API для smoke/альтернативной панели
- `MARZBAN_USERNAME`, `MARZBAN_PASSWORD` - опционально, если access token не задан и нужно получить OAuth token через `/api/admin/token`
- `MARZBAN_USERNAME_PREFIX` - префикс username пользователей в Marzban
- `MARZBAN_DEFAULT_PROXIES`, `MARZBAN_DEFAULT_INBOUNDS` - JSON-настройки proxy/inbound, которые Marzban получит при создании пользователя
- `MARZBAN_DATA_LIMIT_RESET_STRATEGY` - стратегия сброса лимита в Marzban, по умолчанию `no_reset`
- `VULTR_API_TOKEN` - API-токен Vultr для автоскейлера
- `VULTR_DEFAULT_REGION`, `VULTR_DEFAULT_PLAN`, `VULTR_DEFAULT_OS_ID` - параметры создаваемого VPS
- `VULTR_SSH_KEY_IDS` - SSH key ids Vultr через запятую
- `AUTOSCALE_PREMIUM_REGIONS` - регионы warm-pool через запятую, например `ams,fra`; пустое значение оставляет только on-demand provisioning при покупке Premium
- `AUTOSCALE_PREMIUM_MIN_FREE_SLOTS` - минимальный запас свободных premium-мест в каждом warm-регионе
- `AUTOSCALE_PREMIUM_MIN_ACTIVE_NODES` - минимальное число active premium-нод, которые scheduler оставляет в warm-регионе
- `AUTOSCALE_MAX_PROVISIONS_PER_REGION` - лимит новых VPS за один `autoscale_check` на регион
- `DATABASE_URL` - URL PostgreSQL, в compose по умолчанию уже настроен на сервис `postgres`
- `REDIS_URL` - URL Redis, в compose по умолчанию уже настроен на сервис `redis`
- `SUPPORT_USERNAME` - контакт поддержки
- `ADMIN_IDS` - Telegram ID администраторов через запятую

### Single-server Phase 0

Для старта можно использовать один VPS: Remnawave panel, Remnawave node и Host живут на одном сервере, а Host смотрит на публичный IP этого VPS. Для текущей Phase 0 node:

```bash
.venv/bin/python scripts/register_static_node.py \
  --ip 62.60.156.158 \
  --panel-node-id af74d563-a107-4cf0-b4f0-08cad62761d1 \
  --region ams \
  --capacity 50
```

Оставьте `AUTOSCALE_PREMIUM_REGIONS=` пустым, пока не готовы оплачивать дополнительные VPS. Тогда warm-autoscale не будет покупать серверы, а premium capacity будет идти через manual-node из БД.

## Миграции

Docker Compose запускает миграции автоматически перед стартом бота:

```bash
alembic upgrade head
```

Для локального запуска без Docker выполните миграции вручную перед `python main.py`.

## Запуск

```bash
docker compose up -d --build
docker compose logs -f bot
```

При старте compose ждёт healthcheck Postgres/Redis, применяет Alembic-миграции и синхронизирует тарифы в БД.

## Проверка

1. Отправьте боту `/start`.
2. Если Remnawave настроен, бот создаст пробную подписку.
3. Откройте «Моя подписка» и проверьте срок, трафик и subscription-ссылку.
4. Нажмите «Подключить устройство» и импортируйте QR/sub-ссылку в Hiddify, V2RayTun, Streisand или sing-box.
5. Для покупки выберите тариф, оплатите invoice CryptoBot и дождитесь новой/продлённой подписки.

### Multiprotocol profile smoke

Для проверки продуктового сценария "одна ссылка, несколько fallback-протоколов" можно собрать Happ/Xray JSON из endpoint-файла:

```bash
cp docs/examples/client-profile-endpoints.example.json /tmp/unlock-endpoints.json
.venv/bin/python scripts/build_client_profile.py \
  /tmp/unlock-endpoints.json \
  --remarks "UnLock test" \
  --output /tmp/unlock-profile.json
```

Подробнее: `docs/MULTIPROTOCOL_SUBSCRIPTION.md`.

## Legacy AmneziaWG/WireGuard

Если `REMNAWAVE_API_URL`/`REMNAWAVE_API_TOKEN` не заданы, платежный fallback пытается выдавать legacy AmneziaWG-конфиги. Для такого режима бот должен видеть интерфейс `awg0` в том же network namespace.

На Linux-сервере можно запустить legacy override:

```bash
docker compose -f docker-compose.yml -f docker-compose.legacy-wireguard.yml up -d --build
```

В `.env` для legacy режима также нужны:

- `WG_CONFIG_PATH`
- `WG_INTERFACE`
- `WG_SERVER_PUBLIC_KEY`
- `WG_SERVER_ENDPOINT`
- `WG_CLIENT_DNS`
- `WG_ALLOWED_IPS`
- `WG_CLIENT_ADDRESS_POOL`
- `AWG_*` параметры

Бот добавляет клиентов через `awg set <interface> peer ...`, пишет клиентские `.conf` в `WG_CONFIG_PATH` и отправляет пользователю файл + QR.

Минимальный пример серверного `/etc/wireguard/awg0.conf`:

```ini
[Interface]
Address = 10.9.0.1/24
ListenPort = 51821
PrivateKey = SERVER_PRIVATE_KEY
```

```bash
sudo systemctl enable --now awg-quick@awg0
sudo awg show awg0 public-key
```

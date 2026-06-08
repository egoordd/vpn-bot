# Phase 0 Runbook — Remnawave + первая нода

Цель Phase 0: получить живую Remnawave-панель, живую Remnawave Node, рабочую subscription-ссылку и подтвердить браузинг на мобильном клиенте. До этого Фаза 1/2 остаётся mock-verified.

## Что нужно от владельца проекта

Минимальный набор:

- Домен или поддомен для панели, например `panel.example.com`.
- Доступ к DNS, чтобы создать `A` record на IP panel-сервера.
- VPS для панели: Ubuntu/Debian, 2 CPU, 2-4 GB RAM, 20 GB disk.
- VPS для первой ноды: Ubuntu/Debian, 1 CPU, 1 GB RAM минимум. Для Phase 0 допустимо использовать тот же VPS, что и panel.
- SSH-доступ к VPS под `root` или sudo-пользователем.
- Telegram/почта для первого super-admin Remnawave.

Для проверки нашего автоскейлера позже:

- `VULTR_API_TOKEN` с доступом к instances, regions/plans/os/ssh-keys.
- `VULTR_DEFAULT_REGION`, `VULTR_DEFAULT_PLAN`, `VULTR_DEFAULT_OS_ID`.
- `VULTR_SSH_KEY_IDS`, если VPS должны создаваться с SSH key.

## Безопасный формат передачи доступов

Лучше не присылать приватные ключи в чат. Предпочтительные варианты:

- на твоей машине уже настроен SSH key, а ты даёшь только `ssh user@panel_ip` и `ssh user@node_ip`;
- либо создаёшь временного sudo-пользователя и временный ключ специально под установку;
- API-токены кладёшь локально в `.env` и не коммитишь.

## Panel install checklist

На panel-сервере:

```bash
sudo curl -fsSL https://get.docker.com | sh
sudo mkdir -p /opt/remnawave
cd /opt/remnawave
sudo curl -o docker-compose.yml https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/docker-compose-prod.yml
sudo curl -o .env https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/.env.sample
```

Сгенерировать секреты:

```bash
cd /opt/remnawave
sudo sed -i "s/^JWT_AUTH_SECRET=.*/JWT_AUTH_SECRET=$(openssl rand -hex 64)/" .env
sudo sed -i "s/^JWT_API_TOKENS_SECRET=.*/JWT_API_TOKENS_SECRET=$(openssl rand -hex 64)/" .env
sudo sed -i "s/^METRICS_PASS=.*/METRICS_PASS=$(openssl rand -hex 64)/" .env
sudo sed -i "s/^WEBHOOK_SECRET_HEADER=.*/WEBHOOK_SECRET_HEADER=$(openssl rand -hex 64)/" .env
pw=$(openssl rand -hex 24)
sudo sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$pw/" .env
sudo sed -i "s|^\(DATABASE_URL=\"postgresql://postgres:\)[^\@]*\(@.*\)|\1$pw\2|" .env
```

В `.env` панели выставить:

```text
FRONT_END_DOMAIN=panel.example.com
SUB_PUBLIC_DOMAIN=panel.example.com/api/sub
```

Запуск:

```bash
cd /opt/remnawave
sudo docker compose up -d
sudo docker compose logs -f -t
```

## Reverse proxy

Remnawave должен быть доступен с корня домена/поддомена, не в sub-path. Нужен HTTPS reverse proxy на `panel.example.com`, проксирующий panel backend на локальный порт из официального compose.

Acceptance:

```bash
curl -I https://panel.example.com
curl https://panel.example.com/api/auth/status
```

## Первый вход в Panel

1. Открыть `https://panel.example.com`.
2. Создать первого super-admin.
3. Создать API token для бота.
4. Сохранить в `.env` проекта:

```text
REMNAWAVE_API_URL=https://panel.example.com
REMNAWAVE_API_TOKEN=...
REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS=<default-squad-uuid>
```

## Node install checklist

В панели: `Nodes` -> `Management` -> `+`.

Важно:

- `Node Port`, например `2222`.
- Нода слушает внутренний API порт; firewall должен разрешать этот порт только с IP panel-сервера.
- Скопировать generated `docker-compose.yml` из панели.
- После создания node создать `Host` для нужного inbound. Без host и active Internal Squad подписка будет возвращать заглушки вместо рабочих proxy links.
- В single-server режиме Host address должен быть публичным IP этого же VPS, а не `127.0.0.1`.

На node-сервере:

```bash
sudo curl -fsSL https://get.docker.com | sh
sudo mkdir -p /opt/remnanode
cd /opt/remnanode
sudo nano docker-compose.yml
sudo docker compose up -d
sudo docker compose logs -f -t
```

После запуска завершить создание node в панели: выбрать config profile/inbounds и нажать `Create`.

## Live verification

После panel+node:

```bash
set -a
source .env
set +a
.venv/bin/python scripts/remnawave_contract_probe.py --create-user --yes
```

Далее выполнить [LIVE_VERIFICATION.md](./LIVE_VERIFICATION.md).

## Текущая single-server Phase 0

Текущая smoke-инфраструктура использует один сервер:

```text
VPS_PUBLIC_IP=62.60.156.158
REMNAWAVE_NODE_PANEL_UUID=af74d563-a107-4cf0-b4f0-08cad62761d1
REMNAWAVE_HOST_UUID=a48ae2f3-4bfb-4e36-ab58-5bcb96cd3f35
REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS=ce01f98f-1e32-447c-80d7-ab968176ebb1
REMNAWAVE_NODE_CONFIG_PROFILE_UUID=00000000-0000-0000-0000-000000000000
REMNAWAVE_NODE_INBOUND_UUIDS=c18c6a77-bfc9-411a-b70a-8f2c4a6fab3e
REMNAWAVE_NODE_PORT=2222
REMNAWAVE_HOST_PORT=1234
AUTOSCALE_PREMIUM_REGIONS=
```

Дополнительно для smoke был добавлен VLESS Reality inbound на `443/tcp` и Host на тот же публичный IP. Xray client smoke подтвердил, что серверный Reality профиль работает с `flow=xtls-rprx-vision`, но реальный iOS/LTE e2e в Happ/Hiddify не прошёл: Xray видит TLS ClientHello и закрывает соединение с `failed to read client hello`.

По скриншотам рабочего стороннего VPN от 2026-06-05 есть отдельный профиль `JSON США | Hysteria` и несколько auto/anti-DPI JSON-профилей. Поэтому Phase 0 должен проверить Hysteria2 как ранний fallback:

```text
HYSTERIA2_PORT=8443/udp для текущего Aeza smoke; 443/udp только если провайдер пропускает этот порт
HYSTERIA2_AUTH=password
HYSTERIA2_TLS=production domain certificate или self-signed + insecure для smoke
```

UDP-порт можно использовать параллельно с Remnawave/Xray на том же TCP-порту, но текущая Aeza-проверка показала, что `8443/udp` доходит, а `443/udp` выглядит отфильтрованным до VPS.

Для smoke подготовлен скрипт:

```bash
bash scripts/hysteria2_smoketest.sh
```

Он поднимает Hysteria2, печатает `hysteria2://` link и генерирует Happ-compatible JSON в `/opt/hysteria2-smoke/happ-hysteria.json` с тем же каркасом, что у рабочего профиля: socks/http inbounds, `protocol=hysteria`, `version=2`, `alpn=["h3"]`, `fingerprint=chrome`, `congestion=bbr`.

Чтобы приложение считало эту ноду доступной premium-capacity, зарегистрировать ее в БД:

```bash
.venv/bin/python scripts/register_static_node.py \
  --ip 62.60.156.158 \
  --panel-node-id af74d563-a107-4cf0-b4f0-08cad62761d1 \
  --region ams \
  --capacity 50
```

## Acceptance Phase 0

- Панель открывается по HTTPS.
- Первый super-admin создан.
- API token работает.
- Первая Remnawave Node connected/active.
- Тестовый user в панели создаётся и удаляется через probe.
- Subscription URL импортируется в клиент.
- На мобильном операторе есть браузинг через хотя бы один боевой протокол: VLESS/Reality, Hysteria2 или другой подтверждённый fallback.
- Наш бот может создать trial через живую панель.

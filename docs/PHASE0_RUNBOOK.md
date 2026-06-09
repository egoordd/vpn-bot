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

Актуальная single-server smoke-инфраструктура использует месячный VPS:

```text
VPS_PUBLIC_IP=144.172.101.217
NODE_DOMAIN=144.172.101.217.sslip.io
PANEL_PROVIDER=marzban
MARZBAN_API_URL=https://144.172.101.217.sslip.io:8443
VLESS_REALITY_PORT=443/tcp
REALITY_DEST=144.172.101.217:8443
REALITY_SERVER_NAME=144.172.101.217.sslip.io
REALITY_FINGERPRINT=firefox
REALITY_FLOW=xtls-rprx-vision
AUTOSCALE_PREMIUM_REGIONS=
```

Текущий рабочий baseline — Marzban `0.8.4` + VLESS Reality на `443/tcp` + nginx HTTPS на `8443/tcp` с Let's Encrypt сертификатом для `144.172.101.217.sslip.io`. Реальный iPhone по LTE импортировал профиль и получил браузинг без ручного редактирования.

Главный вывод диагностики: чужой SNI вроде `www.microsoft.com` на нашем IP проходит server-side smoke, но может душиться мобильным оператором из-за SNI↔IP корреляции. Для новых нод используем own-domain/self-steal Reality: `address == serverName == домен ноды`, а `dest` ведёт на HTTPS этой же ноды с валидным сертификатом.

Hysteria2 остаётся fallback-протоколом, если конкретная сеть режет TCP Reality:

```text
HYSTERIA2_PORT=8443/udp для текущего Aeza smoke; 443/udp только если провайдер пропускает этот порт
HYSTERIA2_AUTH=password
HYSTERIA2_TLS=production domain certificate или self-signed + insecure для smoke
```

UDP-порт можно использовать параллельно с Xray на том же TCP-порту. Для продукта по умолчанию оставляем VLESS Reality, потому что он уже прошёл реальный iOS/LTE gate.

Для smoke подготовлен скрипт:

```bash
bash scripts/hysteria2_smoketest.sh
```

Он поднимает Hysteria2, печатает `hysteria2://` link и генерирует Happ-compatible JSON в `/opt/hysteria2-smoke/happ-hysteria.json` с тем же каркасом, что у рабочего профиля: socks/http inbounds, `protocol=hysteria`, `version=2`, `alpn=["h3"]`, `fingerprint=chrome`, `congestion=bbr`.

Чтобы приложение считало single-server ноду доступной premium-capacity, зарегистрировать ее в БД:

```bash
.venv/bin/python scripts/register_static_node.py \
  --ip 144.172.101.217 \
  --panel-node-id manual-marzban-144-172-101-217 \
  --region ams \
  --capacity 50
```

## Acceptance Phase 0

- Панель открывается по HTTPS.
- Первый super-admin создан.
- API token работает.
- Первая нода connected/active в выбранной панели.
- Тестовый user в панели создаётся и удаляется через probe.
- Subscription URL импортируется в клиент.
- На мобильном операторе есть браузинг через VLESS Reality в own-domain/self-steal режиме или другой подтверждённый fallback.
- Наш бот может создать trial через живую панель.

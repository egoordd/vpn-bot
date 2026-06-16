# Вторая нода — Amsterdam (Marzban-node) — интеграция

> Поднята и интегрирована 2026-06-16. Проверена с реального телефона (standalone)
> и e2e через панель-управляемый inbound (туннель → выход с IP ноды).

## Что это
Вторая локация для premium, подключённая к **боевой Marzban-панели** как
полноценная нода. Главный inbound `VLESS Reality 443` при этом **не менялся** —
Amsterdam получил свой отдельный inbound с собственным own-domain dest/SNI.

## Инфраструктура ноды
- **VPS:** Cloudzy, Amsterdam, `107.189.22.160` (выделенный IPv4), Ubuntu 24.04,
  0.5 ГБ RAM + 1 ГБ swap. SSH — только по ключу (парольный вход отключён).
- **nginx** на `80` (ACME) и `8443` (self-steal dest, реальный Let's Encrypt серт
  для `107.189.22.160.sslip.io`).
- **marzban-node** (docker, `gozargah/marzban-node`, host-network, REST,
  порты `62050/62051`), сертификат панели в
  `/var/lib/marzban-node/ssl_client_cert.pem`. Конфиг compose в
  `/opt/marzban-node/`.
- **egress-политика** применяется автоматически: BLOCK-правила
  (исходящие 22/25/3389/5432 + `geoip:private`) лежат в боевом **core-config**,
  а он раздаётся на ВСЕ ноды — значит Amsterdam защищён тем же правилом, что и
  главный сервер. Отдельно на ноде держать ничего не нужно (панель перезаписывает
  Xray ноды своим конфигом, но egress в нём уже есть). Подтверждено 2026-06-16.
- Бэкап параметров: `/root/working-reality-backup/` на ноде.

## Панель (боевой главный сервер 144.172.101.217)
- Нода зарегистрирована: `POST /api/node` → `name=Amsterdam`,
  `address=107.189.22.160`, `port=62050`, `api_port=62051`,
  `add_as_new_host=false` (чтобы НЕ создавать Host на главный inbound).
- В core-config (`PUT /api/core/config`) добавлен **отдельный inbound**
  `VLESS Reality AMS`:
  - `port: 2053`, `dest: 107.189.22.160:8443` (локальный nginx ноды),
    `serverNames: [107.189.22.160.sslip.io]`, `shortIds: [a6ec94b3651e91c1]`,
    own keypair ноды (pubkey `n_G4LjyBI8FvOdcgFiYW2UP-hXx1EQaSqiO3HpDA-jc`),
    `flow: xtls-rprx-vision`, `fp: firefox`.
  - Главный `VLESS Reality 443` не тронут.
- Host для `VLESS Reality AMS`: `address/sni=107.189.22.160.sslip.io`,
  `fingerprint=firefox`, `port=null` (берёт 2053 из inbound).

## Почему отдельный inbound (важно)
own-domain Reality привязан к IP: SNI обязан резолвиться в IP ноды, к которой
коннектится клиент, а `dest` — на локальный HTTPS этой же ноды. Поэтому две ноды
с self-steal **не могут делить один inbound** (у inbound один dest/keypair) —
у Amsterdam свой inbound с её dest/SNI/ключами. Главный inbound остаётся на
главном IP.

## Как клиент попадает на Amsterdam
Юзер Marzban, созданный с `inbounds={vless:["VLESS Reality AMS"]}`, получает
в подписке Amsterdam-сервер (`107.189.22.160.sslip.io:2053`). Юзер с главным
inbound — главный сервер. Так premium-локация изолируется от обычной.

## Что осталось (бот)
Бот сейчас создаёт всех юзеров с `MARZBAN_DEFAULT_INBOUNDS=["VLESS Reality 443"]`.
Чтобы premium-юзер с регионом `ams` реально попадал на Amsterdam, нужно:
1. Маппинг региона → inbound tag (`ams → "VLESS Reality AMS"`).
2. Создание premium-юзера в Marzban с этим inbound (правка
   `services/marzban_client.py` / `panel_gateway` / `subscription`).
3. Снять блокировку оплаты premium с баланса для статической ноды (в чекауте).

## TODO / хвосты
- **Бот:** premium-юзер с регионом `ams` → создание в Marzban с inbound
  `VLESS Reality AMS` (см. раздел выше). Это финальный шаг, чтобы premium стал
  реально покупаемым и роутился на Amsterdam.
- Health-мониторинг ноды (нода в панели = `connected`; алерт при `error`).
- Авто-renew LE-серта на ноде (certbot timer).

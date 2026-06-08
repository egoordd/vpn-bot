# Live Verification Gate

Этот документ фиксирует обязательный стоп-кран перед Фазой 3. Текущая Фаза 1/2 покрыта pytest и моками, но не считается боевой, пока не пройдены проверки ниже на живой Remnawave, живой ноде и реальном Vultr API.

## 1. Remnawave API contract

Требуется `.env` с:

- `REMNAWAVE_API_URL`
- `REMNAWAVE_API_TOKEN`
- `REMNAWAVE_DEFAULT_TRAFFIC_RESET_STRATEGY`

Проверка чтения:

```bash
set -a
source .env
set +a
.venv/bin/python scripts/remnawave_contract_probe.py
```

Проверка создания/чтения/sub-link/удаления тестового пользователя:

```bash
.venv/bin/python scripts/remnawave_contract_probe.py --create-user --yes
```

Acceptance:

- `/api/keygen` возвращает ожидаемый ключ для Remnawave Node.
- `POST /api/users` принимает payload из `services/panel_client.py`.
- `GET /api/users/by-username/{username}` возвращает поля, которые парсит `PanelUser`.
- protected subscription endpoint возвращает `subscriptionUrl`.
- тестовый пользователь удаляется.

## 2. Vultr API contract

Требуется `.env` с:

- `VULTR_API_TOKEN`
- `VULTR_DEFAULT_REGION`
- `VULTR_DEFAULT_PLAN`
- `VULTR_DEFAULT_OS_ID`
- `VULTR_SSH_KEY_IDS` если SSH key обязателен

Проверка без создания VPS:

```bash
.venv/bin/python scripts/vultr_contract_probe.py
```

Acceptance:

- токен валиден;
- регион, план и OS ID существуют;
- указанные SSH key IDs существуют либо список пустой осознанно.

## 3. Autoscaler live create/register/delete

Требуется полный `.env`:

- Remnawave: `REMNAWAVE_API_URL`, `REMNAWAVE_API_TOKEN`, `REMNAWAVE_DEFAULT_INTERNAL_SQUAD_UUIDS`, `REMNAWAVE_NODE_CONFIG_PROFILE_UUID`, `REMNAWAVE_NODE_INBOUND_UUIDS`, `REMNAWAVE_NODE_PORT`, `REMNAWAVE_HOST_PORT`
- Vultr: `VULTR_API_TOKEN`, `VULTR_DEFAULT_REGION`, `VULTR_DEFAULT_PLAN`, `VULTR_DEFAULT_OS_ID`, `VULTR_SSH_KEY_IDS`, `VULTR_NODE_CAPACITY`

Создаёт платный Vultr VPS, регистрирует ноду в Remnawave и затем удаляет оба ресурса:

```bash
.venv/bin/python scripts/live_autoscaler_probe.py --yes
```

Acceptance:

- Vultr instance создан и получил `main_ip`.
- Remnawave node создан через API и имеет `panelNodeId`.
- Remnawave Host создан для inbound и IP новой node.
- cleanup удалил Remnawave Host, Remnawave node и Vultr instance.
- Если cleanup не прошёл, удалить ресурсы вручную в Vultr/Remnawave до продолжения.

## 3a. Static single-server node

Если используется один оплаченный VPS без Vultr autoscale, регистрируем уже созданную Remnawave node в БД приложения:

```bash
.venv/bin/python scripts/register_static_node.py \
  --ip 62.60.156.158 \
  --panel-node-id af74d563-a107-4cf0-b4f0-08cad62761d1 \
  --region ams \
  --capacity 50
```

Acceptance:

- В таблице `nodes` есть запись `provider=manual`.
- `ip_address` равен публичному IP текущего VPS.
- `panel_node_id` равен UUID node из Remnawave.
- `AUTOSCALE_PREMIUM_REGIONS` пустой, если новые VPS пока оплачивать не нужно.

## 4. Real user e2e

После успешных contract probes:

1. Запустить бота с живой Remnawave.
2. `/start` должен создать trial user в панели.
3. В боте должна появиться subscription-ссылка.
4. Импортировать ссылку в Hiddify/V2RayTun/Streisand/sing-box.
5. Проверить браузинг на мобильном операторе.
6. Проверить `traffic_sync`: трафик должен обновиться в кабинете.
7. Проверить покупку Standard через CryptoBot test/real flow.
8. Проверить Premium: выбор региона, назначение/подъём ноды, отображение локации.

До прохождения этого списка Фаза 1/2 считается mock-verified, а не production-ready.

## Phase 0 live notes, 2026-06-08

Текущий месячный VPS: `144.172.101.217`, Ubuntu 24.04.3, Marzban `0.8.4`.

- Marzban API/dashboard доступен через Nginx `80/tcp`, backend слушает только `127.0.0.1:8000`.
- Клиентские подписки доступны по HTTPS на `8443/tcp`: `https://144.172.101.217.sslip.io:8443`, сертификат Let's Encrypt доверенный.
- Xray слушает `443/tcp` для `VLESS Reality 443` и `1080/tcp,udp` для `Shadowsocks TCP`.
- IPv6 отключён на уровне sysctl, глобальный IPv6 адрес снят, nginx больше не слушает `[::]:80`.
- Marzban настроен отдавать Happ/Xray JSON: `USE_CUSTOM_JSON_FOR_HAPP=True`, `V2RAY_SUBSCRIPTION_TEMPLATE="v2ray/happ.json"`.
- Явный endpoint `/sub/{token}/v2ray-json` снаружи по HTTPS возвращает `200 application/json`; обычный `/sub/{token}` под `User-Agent: Happ/4.10.0` тоже возвращает JSON.
- JSON содержит DNS `queryStrategy=UseIPv4`, локальные inbounds `127.0.0.1:10808` socks и `127.0.0.1:10809` http, не содержит удалённый Xray-параметр `allowInsecure`.
- `xray run -test` проходит на первом VLESS Reality JSON-профиле.
- Server-side Xray client smoke через этот JSON проходит: запрос через socks `127.0.0.1:10808` возвращает внешний IP `144.172.101.217`, а `http://www.gstatic.com/generate_204` возвращает `204 No Content`.
- После iOS/Happ теста 2026-06-08 подписка скачалась (`Happ/4.10.2/ios`, `200 OK`), пользователь стал `online_at=2026-06-08T00:05:19`, traffic counter вырос, но браузинга на телефоне нет. Это исключает проблему QR/HTTPS/импорта и указывает на runtime/outbound path.
- Marzban `v2ray-json` отдаёт массив из двух отдельных конфигов, где первым идёт `VLESS Reality 443`, а вторым `Shadowsocks TCP`. С учётом предыдущих iOS/LTE failures для Reality это главный подозреваемый: Happ может запускать/выбирать первый Reality профиль, а не fallback.
- Для изоляции создан отдельный HTTPS JSON-объект только с Shadowsocks: `/profiles/<token>/happ-ss-only.json`. Он не массив, не содержит VLESS/Reality, проходит `xray run -test`, server-side Xray client smoke через него возвращает `api.ipify.org=144.172.101.217` и `gstatic/generate_204=204`.
- После замечания, что целевой продукт должен быть именно VLESS, тестовый пользователь переведён на `flow=xtls-rprx-vision`. Marzban пересоздал VLESS UUID, поэтому старые QR стали неактуальны.
- Создан отдельный HTTPS JSON-объект только с VLESS/Vision: `/profiles/<new-token>/happ-vless-vision-domain.json`. Отличия от стандартной Marzban-подписки: один JSON-объект вместо массива, только VLESS outbound, `flow=xtls-rprx-vision`, `address=144.172.101.217.sslip.io`, Reality `serverName=www.microsoft.com`. Профиль проходит `xray run -test` и server-side Xray client smoke (`api.ipify.org=144.172.101.217`, `gstatic/generate_204=204`).

Остаётся решающий gate: импорт QR/URL на реальном iOS LTE в Happ/Hiddify и фактический браузинг без ручного редактирования профиля.

## Phase 0 live notes, 2026-06-04

> 2026-06-07: VPS `62.60.156.158` больше не актуален: сервер был удалён у провайдера из-за простоя/непродления. Все результаты ниже остаются полезными как история диагностики, но новый Phase 0 gate нужно повторить на новом IP.

Single-server Remnawave smoke на `62.60.156.158` поднят и проверен:

- Remnawave backend healthy, Remnawave Node up.
- Xray слушает `443/tcp` для VLESS Reality и `1234/tcp` для Shadowsocks.
- Подписка отдает оба proxy link через текущий HTTPS tunnel.
- `FRONT_END_DOMAIN` и `SUB_PUBLIC_DOMAIN` на сервере обновлены с умершего tunnel на текущий tunnel.
- Независимый Xray client smoke через VLESS Reality прошел: `flow=xtls-rprx-vision` обязателен.
- Вариант VLESS Reality без `flow` не проходит.
- Независимый Xray client smoke через Shadowsocks прошел.

Результаты реального iOS/LTE smoke:

- VLESS Reality через Remnawave и чистый standalone Xray проходит на сервере и с внешнего Mac/sing-box, но не проходит в Happ/Hiddify на iOS LTE.
- Tcpdump с телефона показывает TLS ClientHello на `443/tcp`, но Xray закрывает соединение с `failed to read client hello`; перебор `flow`, `sni` и `fingerprint` (`chrome`, `ios`, `firefox`, `safari`, `randomized`) не дал мобильного браузинга.
- Чистый Shadowsocks на `443/tcp` проходит внешний Mac/sing-box smoke; iOS-клиент доходит до сервера, но попытка через импортированный link была отклонена как `failed to match an user`, то есть проблема была уже в формате/импорте SS-профиля, а не в доступности VPS.
- Hysteria2 smoke сначала был поднят на `443/udp`, но этот порт на Aeza не показал нормальный входящий packet capture. Повторная проверка 2026-06-06 показала, что входящий UDP до VPS в целом работает: сырые UDP-пакеты с внешнего Mac стабильно приходят на `8443`, `2053` и `12345`. Hysteria2 перенесён на `8443/udp`; `ufw inactive`, локальный firewall не выглядит причиной.
- Дополнительный VLESS Reality smoke на `8443/tcp` с доменным `address=62.60.156.158.sslip.io`, `fingerprint=firefox`, `flow=xtls-rprx-vision` проходит внешний Mac/sing-box smoke, но iOS/Happ снова даёт `failed to read client hello`. Tcpdump показывает первый TCP payload `1308` bytes с TLS ClientHello record length около `0x075f`; остаток ClientHello до сервера не приходит.

Скриншоты и JSON рабочего стороннего VPN от 2026-06-05 показывают, что рабочий набор не ограничен VLESS Reality:

- есть отдельный профиль `JSON США | Hysteria`;
- есть профили `JSON АВТО-ОБХОД`, `JSON Обход глушилок I`, `JSON Обход глушилок X`;
- JSON-каркас использует локальные inbounds `127.0.0.1:10808` socks и `127.0.0.1:10809` http, DNS `UseIPv4`, sniffing `http/tls/quic`;
- auto-профиль использует `burstObservation` с `http://www.gstatic.com/generate_204` и selector `proxy`.
- рабочий VLESS Reality outbound: `network=tcp`, `security=reality`, `flow=xtls-rprx-vision`, `fingerprint=firefox`, `address` и `serverName` равны домену ноды, не голому IP и не внешнему decoy-домену;
- рабочий Hysteria outbound: `protocol=hysteria`, `version=2`, `network=hysteria`, `security=tls`, `alpn=["h3"]`, `fingerprint=chrome`, `congestion=bbr`, `serverName` равен домену ноды.
- Happ/XrayCore 4.10.0 не принимает `allowInsecure`; для self-signed smoke TLS нужно генерировать `pinnedPeerCertSha256` по сертификату сервера.

Следующий обязательный live gate: проверить Hysteria2 на этой же ноде через `8443/udp` в Happ/Hiddify на iOS LTE. Для боевого варианта можно оставить нестандартный UDP-порт, либо запросить у Aeza открытие/исключение для `443/udp`. Для точного клонирования рабочего профиля нужен полный JSON ниже секции `outbounds`, а не только верхние скриншоты.

Для production временный `trycloudflare.com` нужно заменить на стабильный домен.

# Рабочая VPN-конфигурация (VLESS+Reality) — ЗАКРЕПЛЕНО

> Проверено на реальном iPhone по LTE российского оператора: **2026-06-08 — работает.**
> Это первая конфигурация, которая реально пробила оператора после многократных провалов.

## Корень проблемы «подключается, но интернета нет»

Оператор делает **SNI↔IP корреляцию**. Наш Reality слал SNI `www.microsoft.com`, подключаясь к нашему IP `144.172.101.217` (который не принадлежит Microsoft). Оператор видел несоответствие → помечал как прокси → душил поток. Серверный smoke этого не ловит (в пути нет оператора), поэтому он «проходил» 3+ раза и вводил в заблуждение.

## Решение — own-domain Reality (self-steal), как у SaveVPN

Используем SNI, который **резолвится в наш же IP** → для оператора это обычный заход на реальный домен.

**Серверные параметры (Marzban inbound `VLESS Reality 443`):**
- `serverNames = ["144.172.101.217.sslip.io"]` — резолвится в наш IP (sslip.io, бесплатно).
- `dest = "144.172.101.217:8443"` — локальный nginx Marzban с **настоящим Let's Encrypt-сертификатом** для этого домена, TLS 1.3 (= self-steal/прикрытие реальным сайтом).
- keypair прежний (privateKey в конфиге; publicKey ниже).

**Marzban Host (db.sqlite3, чтобы подписка отдавала рабочее):**
- `address = 144.172.101.217.sslip.io`
- `sni = 144.172.101.217.sslip.io`
- `fingerprint = firefox`  ← (SaveVPN использует firefox, не chrome)

**Итоговый клиентский конфиг (что отдаёт бот и что заработало):**
```
address/serverName : 144.172.101.217.sslip.io
port               : 443
security           : reality
flow               : xtls-rprx-vision
fingerprint        : firefox
publicKey          : XfIFLXO4LUizIpiNXay1p8HL_ou5thasFS5bPusNziw
shortId            : 3684c6d01d7363a4
```
vless-ссылка (пример с тест-UUID):
```
vless://<uuid>@144.172.101.217.sslip.io:443?type=tcp&security=reality&pbk=XfIFLXO4LUizIpiNXay1p8HL_ou5thasFS5bPusNziw&fp=firefox&sni=144.172.101.217.sslip.io&sid=3684c6d01d7363a4&flow=xtls-rprx-vision&encryption=none#UnLock-Reality
```

## Бэкап на сервере
`/root/working-reality-backup/` — `xray_config.json.WORKING`, `db.sqlite3.before-host-fix`, `WORKING_PARAMS.txt`.

## Правило для новых нод
Любая новая нода ДОЛЖНА подниматься в этом режиме: SNI = домен, резолвящийся в IP ноды (sslip.io или реальный домен) + реальный TLS-сертификат для dest + fingerprint firefox. **Никогда** не использовать чужой SNI (microsoft и т.п.) на нашем IP — оператор это душит.

## Запасной протокол
На сервере также поднят **Hysteria2** (`udp/443`, self-signed, пароль в `/etc/hysteria/config.yaml`) — server-side проверен; держим как fallback, если Reality где-то не пройдёт. QR: `~/Desktop/hysteria_qr.png`.

## Egress-политика ноды (анти-abuse) — применено 2026-06-10
Юзерский трафик выходит с IP ноды, поэтому исходящие сервисные порты заблокированы,
чтобы ноду не использовали как плацдарм (брутфорс/спам → abuse-жалобы → бан VPS,
блэклисты IP):

- **Xray** (`/var/lib/marzban/xray_config.json`, routing → BLOCK/blackhole):
  - `port: 22,25,3389,5432` (tcp+udp) — SSH-брутфорс, спам, RDP, Postgres;
  - `ip: geoip:private` — из туннеля нельзя достучаться до localhost/LAN/панели.
- **Hysteria2** (`/etc/hysteria/config.yaml`, `acl.inline`): те же порты + private CIDR.

Проверено через туннель: HTTPS работает (ya.ru 302), `:25`/`:22` блокируются.
Бэкапы конфигов: `*.bak-YYYYMMDD-HHMMSS` рядом с оригиналами.
**Правило для новых нод:** этот egress-блок обязателен при провижининге (внести в
cloud-init/autoscaler setup при live-подключении Vultr).

## Связанные
- `PROJECT_CONTEXT.md`, `IMPLEMENTATION_PLAN.md`
- `docs/examples/saveworking_nl_reality.json` / `saveworking_us_hysteria.json` — рабочие референсы SaveVPN, по которым чинили.

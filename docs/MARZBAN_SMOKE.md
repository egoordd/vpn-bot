# Marzban Smoke Path

Marzban можно использовать как быстрый baseline для новой ноды: панель создаёт пользователей, отдаёт subscription URL и управляет Xray inbounds. В коде подготовлен отдельный API-клиент `services/marzban_client.py`; он не заменяет Remnawave автоматически, пока live gate не пройден.

## Что Нужно От VPS

Минимум для smoke:

- Ubuntu 22.04/24.04;
- `22/tcp` для SSH;
- `80/tcp` для dashboard/subscription через reverse proxy к локальному Marzban `127.0.0.1:8000`;
- `8000/tcp` только временно для Marzban dashboard, если нет reverse proxy;
- `443/tcp` для Reality/Trojan;
- `8443/udp` и/или `443/udp` для Hysteria2 fallback, если поднимаем рядом;
- домен желательно, но для первого panel smoke можно начать с IP/временного HTTPS tunnel.

## Env Для Кода

```env
PANEL_PROVIDER=marzban
MARZBAN_API_URL=https://panel.example.com
MARZBAN_ACCESS_TOKEN=
MARZBAN_USERNAME=admin
MARZBAN_PASSWORD=replace_with_admin_password
MARZBAN_USERNAME_PREFIX=tg
MARZBAN_DEFAULT_PROXIES={"vless":{}}
MARZBAN_DEFAULT_INBOUNDS={"vless":["VLESS TCP REALITY"]}
MARZBAN_DATA_LIMIT_RESET_STRATEGY=no_reset
```

Если известен долгоживущий access token, можно заполнить только `MARZBAN_ACCESS_TOKEN`; иначе клиент получает token через `/api/admin/token`.

`MARZBAN_DEFAULT_PROXIES` и `MARZBAN_DEFAULT_INBOUNDS` должны соответствовать названиям inbound в Marzban. После установки панели сначала создаём/проверяем тестового пользователя в dashboard, затем переносим эти значения в `.env`.

Для текущего месячного VPS от 2026-06-08 значения:

```env
PANEL_PROVIDER=marzban
MARZBAN_API_URL=https://144.172.101.217.sslip.io:8443
MARZBAN_USERNAME=codex_admin
MARZBAN_DEFAULT_PROXIES={"vless":{},"shadowsocks":{}}
MARZBAN_DEFAULT_INBOUNDS={"vless":["VLESS Reality 443"],"shadowsocks":["Shadowsocks TCP"]}
MARZBAN_DATA_LIMIT_RESET_STRATEGY=no_reset
```

Пароль `codex_admin` хранится только на сервере: `/root/marzban_codex_admin.env`.

## Поддержанный API-Контракт

Клиент покрывает:

- `POST /api/admin/token` — получить OAuth password token;
- `POST /api/user` — создать пользователя;
- `GET /api/user/{username}` — прочитать статус, usage, links, `subscription_url`;
- `PUT /api/user/{username}` — продлить/изменить лимиты/status;
- `DELETE /api/user/{username}` — удалить пользователя.

Marzban `0.8.4` может вернуть `subscription_url` относительным (`/sub/...`). `services/marzban_client.py` нормализует его до полного URL через `MARZBAN_API_URL`, чтобы бот не отдавал пользователю непригодную ссылку.

## Contract Probe

Живую проверку можно повторить одной командой:

```bash
MARZBAN_PASSWORD="$(ssh -i /Users/egoordd/.ssh/id_ed25519 root@144.172.101.217 "sed -n 's/^MARZBAN_PASSWORD=//p' /root/marzban_codex_admin.env | head -n1")" \
.venv/bin/python scripts/marzban_contract_probe.py \
  --base-url https://144.172.101.217.sslip.io:8443 \
  --username codex_admin \
  --create-user \
  --yes
```

По умолчанию probe не печатает прямые client links, только протоколы. Для ручного QR/debug можно добавить `--print-links`.

## Current Monthly VPS 2026-06-08

Сервер `144.172.101.217`, Ubuntu 24.04.3, Marzban `0.8.4`.

Поднято:

- 1 GiB swap, потому что VPS имеет 458 MiB RAM;
- Marzban container `gozargah/marzban:latest` на host network;
- Marzban dashboard/API остаётся на `127.0.0.1:8000`;
- Nginx reverse proxy слушает `80/tcp` по IPv4 для dashboard/ACME и `8443/tcp` по HTTPS для клиентских подписок;
- Xray слушает `443/tcp` для `VLESS Reality 443`;
- Xray слушает `1080/tcp,udp` для дефолтного `Shadowsocks TCP`;
- внешний `nc` подтвердил доступность `80/tcp` и `443/tcp`.

Изменения на сервере:

- `/var/lib/marzban/xray_config.json` дополнен inbound `VLESS Reality 443`;
- reality private key и short id сохранены в `/root/reality_443.env`;
- `/opt/marzban/.env` получил `XRAY_SUBSCRIPTION_URL_PREFIX=https://144.172.101.217.sslip.io:8443`;
- `/opt/marzban/.env` получил `CUSTOM_TEMPLATES_DIRECTORY`, `V2RAY_SUBSCRIPTION_TEMPLATE` и `USE_CUSTOM_JSON_FOR_HAPP=True`;
- `/var/lib/marzban/templates/v2ray/happ.json` отдаёт Happ/Xray JSON с `UseIPv4`, локальными inbounds `127.0.0.1` и без устаревшего `allowInsecure`;
- Let's Encrypt сертификат выпущен для `144.172.101.217.sslip.io`, потому что Happ запрещает небезопасные `http://` subscription URL;
- IPv6 отключён через `/etc/sysctl.d/99-disable-ipv6.conf`, глобальный IPv6 адрес снят, `listen [::]:80` удалён из nginx;
- тестовый пользователь `codex_smoke` оставлен для ручной проверки телефона: 30 дней, 10 GiB.

Live gate на уровне API пройден:

- `GET /api/system`;
- `GET /api/inbounds`;
- `POST /api/user`;
- `GET /api/user/{username}`;
- `PUT /api/user/{username}`;
- `DELETE /api/user/{username}`.

Server-side Happ JSON e2e пройден: `GET /sub/{token}/v2ray-json` по HTTPS снаружи возвращает `200 application/json` с доверенным сертификатом, Happ User-Agent на обычном `/sub/{token}` тоже получает JSON, `xray run -test` проходит, а запуск первого JSON-профиля как локального Xray-клиента даёт браузинг через SOCKS (`api.ipify.org` возвращает `144.172.101.217`, `gstatic/generate_204` возвращает `204 No Content`).

После ручной диагностики Happ/iOS стало ясно, что проблема была не в QR, HTTPS, JSON или клиенте. Нерабочие VLESS Reality варианты использовали чужой `serverName` (`www.microsoft.com`) при подключении к нашему IP; мобильный оператор коррелировал `SNI` и IP и душил поток. Серверный smoke этого не ловил.

Рабочий VLESS Reality зафиксирован так:

```text
address/serverName = 144.172.101.217.sslip.io
dest               = 144.172.101.217:8443
port               = 443
security           = reality
flow               = xtls-rprx-vision
fingerprint        = firefox
shortId            = 3684c6d01d7363a4
publicKey          = XfIFLXO4LUizIpiNXay1p8HL_ou5thasFS5bPusNziw
```

`dest` указывает на nginx HTTPS с Let's Encrypt сертификатом для `144.172.101.217.sslip.io`, то есть Reality прикрывается реальным TLS-сервисом этой же ноды. Этот вариант импортирован на реальном iPhone по LTE и даёт фактический браузинг. Бэкап рабочего состояния лежит на сервере в `/root/working-reality-backup/`.

Phase 0 для текущего single-server Marzban path закрыт. Для новых нод нельзя возвращаться к чужому SNI; нужно повторять own-domain/self-steal схему из `docs/WORKING_VPN_CONFIG.md` и `scripts/reality_smoketest.sh`.

## Happ JSON QR

Для Happ нельзя считать QR с сырым JSON надёжным импортом профиля: приложение обычно ожидает URL подписки или URI-ссылку, а полный JSON должно скачать само. Поэтому для теста нужно сканировать URL:

```text
https://144.172.101.217.sslip.io:8443/sub/<token>/v2ray-json
```

Явный `/v2ray-json` не зависит от User-Agent. Обычный `/sub/<token>` тоже отдаёт JSON для `Happ/4.10.0`, потому что на сервере включён `USE_CUSTOM_JSON_FOR_HAPP=True`.

Предыдущий одноразовый smoke `91.108.240.76` больше не считается текущей инфраструктурой.

## Smoke Сценарий

1. Установить Marzban и создать admin.
2. Настроить хотя бы один inbound VLESS Reality на `443/tcp`.
3. Создать тестового пользователя через панель и убедиться, что Marzban отдаёт subscription URL.
4. Импортировать subscription URL в Happ/Hiddify на iOS LTE.
5. Проверить реальный браузинг на iOS LTE без ручного редактирования профиля.

Phase 0 считается закрытой только после реального браузинга на телефоне. Для текущего VPS `144.172.101.217` этот gate пройден.

# Multiprotocol Subscription Profile

Цель этого слоя: пользователь получает одну ссылку/QR, а клиент внутри профиля сам пробует несколько proxy-вариантов. Пользователь не выбирает протокол, порт или приложение вручную.

Текущий генератор строит Happ/Xray-compatible JSON:

- VLESS Reality over TCP;
- Hysteria2 over UDP;
- Shadowsocks;
- Trojan over TLS;
- socks/http local inbounds;
- DNS `UseIPv4`;
- sniffing `http`, `tls`, `quic`;
- `burstObservatory` + routing balancer `leastPing`, если proxy больше одного;
- `direct` rules для push/RU-сервисов/private IP;
- `block` rule для BitTorrent.

## Generate A Test Profile

Подготовить endpoint-файл:

```bash
cp docs/examples/client-profile-endpoints.example.json /tmp/unlock-endpoints.json
```

Заменить значения на реальные параметры ноды и собрать профиль:

```bash
.venv/bin/python scripts/build_client_profile.py \
  /tmp/unlock-endpoints.json \
  --remarks "UnLock test" \
  --output /tmp/unlock-profile.json
```

Minified JSON для subscription endpoint:

```bash
.venv/bin/python scripts/build_client_profile.py \
  /tmp/unlock-endpoints.json \
  --remarks "UnLock test" \
  --compact \
  --output /tmp/unlock-profile.min.json
```

Дальше `/tmp/unlock-profile.json` можно отдать через HTTPS endpoint и импортировать в Happ/Hiddify как JSON/subscription URL.

## Endpoint Schema

VLESS Reality:

```json
{
  "protocol": "vless-reality",
  "tag": "nl-reality-443",
  "server": "node.example.com",
  "server_port": 443,
  "id": "user-uuid",
  "pbk": "reality-public-key",
  "sni": "node.example.com",
  "sid": "short-id",
  "fingerprint": "firefox",
  "flow": "xtls-rprx-vision"
}
```

Hysteria2:

```json
{
  "protocol": "hysteria2",
  "tag": "nl-hy2-8443",
  "server": "node.example.com",
  "server_port": 8443,
  "password": "auth-secret",
  "sni": "node.example.com",
  "fingerprint": "chrome",
  "alpn": ["h3"],
  "congestion": "bbr",
  "pin_sha256": "optional_self_signed_certificate_sha256"
}
```

Shadowsocks:

```json
{
  "protocol": "shadowsocks",
  "tag": "nl-ss-1234",
  "server": "node.example.com",
  "server_port": 1234,
  "method": "chacha20-ietf-poly1305",
  "password": "ss-password"
}
```

Trojan TLS:

```json
{
  "protocol": "trojan",
  "tag": "nl-trojan-443",
  "server": "node.example.com",
  "server_port": 443,
  "password": "trojan-password",
  "sni": "node.example.com",
  "fingerprint": "chrome",
  "alpn": ["http/1.1"]
}
```

## Live Gate

Этот генератор закрывает только кодовую часть пункта 41 из `IMPLEMENTATION_PLAN.md`. Production-ready статус появляется только после реального gate:

1. Новый VPS доступен по TCP/UDP.
2. Reality, Hysteria2 и хотя бы один fallback реально слушают на ноде.
3. JSON импортируется в Happ/Hiddify без ручного редактирования.
4. На iOS/LTE есть браузинг.
5. При отключении одного proxy клиент уходит на другой без участия пользователя.

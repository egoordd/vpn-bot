# RU-relay — обход белых списков через российский VPS-релей

Метод из статьи Habr 1021160 / `github.com/Sergei-thinker/vpn-setup` (`deploy-relay.sh`).
Заменяет тупиковый путь vk-turn/Телемост (сломан провайдерами). Надёжен, переиспользует
нашу живую VLESS Reality.

## Идея
```
Клиент (РФ, мобилка) → РФ-VPS релей :443 (Reality, SNI www.gosuslugi.ru)
                     → наша загран-нода (PL Reality :2087) → интернет
```
ТСПУ фильтрует по IP: **РФ-адрес релея проходит** (не в блоке/в белых списках), SNI
`www.gosuslugi.ru` — госсайт, всегда доступен. Релей **ре-терминирует** VLESS и делает
второй VLESS-Reality наружу на нашу ноду (её IP видит только релей из РФ-ДЦ, где egress
свободнее; Reality маскирует и этот хоп).

## Что нужно от юзера
- Дешёвый **российский VPS** (Timeweb / VDSina / Selectel / aeza-ru), ~150–300₽/мес,
  Ubuntu 22.04/24.04, чистый РФ-IP, root SSH. (Юр-нюанс: VPS под РФ-юрисдикцией — риск на юзере.)

## Установка на РФ-VPS (я делаю по SSH)
1. Xray-core (standalone, без панели): `bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install`
2. Сгенерить reality-ключи релея: `xray x25519` (→ RELAY_PRIV/RELAY_PBK), shortId `openssl rand -hex 8`.
3. Создать выделенного юзера на нашей PL-панели (Marzban) для outbound → получить `RELAY_OUT_UUID`.
4. `/usr/local/etc/xray/config.json`:
```json
{
  "inbounds": [{
    "tag": "relay-in", "listen": "0.0.0.0", "port": 443, "protocol": "vless",
    "settings": {"clients": [{"id": "CLIENT_UUID", "flow": "xtls-rprx-vision"}], "decryption": "none"},
    "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {
      "dest": "www.gosuslugi.ru:443", "serverNames": ["www.gosuslugi.ru"],
      "privateKey": "RELAY_PRIV", "shortIds": ["RELAY_SID"]}}
  }],
  "outbounds": [{
    "tag": "to-node", "protocol": "vless",
    "settings": {"vnext": [{"address": "78.17.154.225", "port": 2087,
      "users": [{"id": "RELAY_OUT_UUID", "flow": "xtls-rprx-vision", "encryption": "none"}]}]},
    "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {
      "serverName": "78.17.154.225.sslip.io",
      "publicKey": "B94gt5HcRpinXwbnQFFjRV1ZMNA0Da38-7Aej69Y8TA",
      "shortId": "39fb8b580ab91c5d", "fingerprint": "firefox"}}
  }],
  "routing": {"rules": [{"type": "field", "inboundTag": ["relay-in"], "outboundTag": "to-node"}]}
}
```
5. `systemctl enable --now xray`; открыть :443; проверить egress: клиент → релей → выход = наш загран-IP.

## Клиентская ссылка (для юзеров)
```
vless://CLIENT_UUID@RU_RELAY_IP:443?type=tcp&security=reality&flow=xtls-rprx-vision&sni=www.gosuslugi.ru&pbk=RELAY_PBK&sid=RELAY_SID#🇷🇺→🌍 Антиблок
```
Импортируется в **Happ** как обычный VLESS — в отличие от vk-turn, тут **одна ссылка**, one-tap.
→ можно добавить в подписку как ещё одну «локацию»/аварийный вход через шлюз.

## Апгрейд (позже)
- Outbound релея на **xhttp+reality** (нужен xhttp-inbound на ноде) — крепче на хопе релей→нода.
- SNI-ротация (`deploy-sni-rotation.sh`), IP-leak block, split-routing РФ-подсетей.
- Несколько РФ-релеев для надёжности; выбор провайдера (у которого IP не «палёный»).

## Почему это лучше vk-turn/Телемоста
Стандартный chaining, а не абуз чужого API: провайдеры не могут «сломать» это версией/капчей.
Единственная зависимость — доступность РФ-IP релея (можно менять). One-tap в Happ.

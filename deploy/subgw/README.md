# Subscription gateway on the bot VPS (23.95.3.18)

Runbook for `unlock-subgw` after the 2026-07-11 move off the US node.
The US node (458 MB RAM) was a single point of failure: when it died, every
client's subscription went blank regardless of location. The gateway now runs
on the control VPS behind Caddy on :443; the US copy stays up only for legacy
`sub.unlockvpn.site:8444` links until DNS is repointed.

## Layout

| Piece | Where |
|---|---|
| Script | `/opt/sub_gateway.py` (copy of `services/sub_gateway.py`) |
| Env | `/etc/unlock-subgw.env` (chmod 600; Hy2/Trojan node passwords live here) |
| Unit | `/etc/systemd/system/unlock-subgw.service` (this dir keeps the template) |
| TLS + routing | Caddy (`/etc/caddy/Caddyfile`), gateway is plain HTTP on 127.0.0.1:8090 |

Env on the VPS (no CERT_FILE/KEY_FILE — Caddy terminates TLS):

```
MARZBAN_BASE=https://144.172.101.217.sslip.io:8443
BIND_HOST=127.0.0.1
LISTEN_PORT=8090
US_HY2_PASS=…
NL_HY2_PASS=…
PL_HY2_PASS=…
PL_TROJAN_PASS=…
```

## Caddy routing

`/sub/*` and `/happ/*` on the public hosts proxy to 127.0.0.1:8090; everything
else keeps going to the billing API on :8080. Hosts:

- `23.95.3.18.sslip.io` — always-on base, used as `SUB_GATEWAY_URL` while
  unlockvpn.site is on registrar clientHold.
- `sub.unlockvpn.site` + `https://sub.unlockvpn.site:8444` — activate by
  pointing the A-record at 23.95.3.18 once the domain is unblocked; :8444
  serves links cached by old clients (needs `ufw allow 8444/tcp`).

## Deploy an update

```
scp -i ~/.ssh/vpnbot_vps services/sub_gateway.py root@23.95.3.18:/opt/sub_gateway.py
ssh -i ~/.ssh/vpnbot_vps root@23.95.3.18 systemctl restart unlock-subgw
```

## Verify

```
curl -s https://23.95.3.18.sslip.io/sub/<active-token> | base64 -d   # full link set
curl -s https://23.95.3.18.sslip.io/sub/<expired-token>              # empty body
```

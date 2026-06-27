# Trojan protocol — deploy runbook

Bot/gateway side is **done** (commit `feat(gateway): pass through all proxy
protocols`). The gateway now forwards any `trojan://` link Marzban issues. What
remains is panel-side: (1) a Trojan inbound in xray, (2) granting users a
`trojan` proxy via env. Both run on the nodes, not in this repo.

> ⚠️ **RAM gate.** The US node (144.172.101.217, 1 vCPU / 458 MB) runs with
> ~17 MB free. A new xray TLS inbound costs memory; per HANDOFF this can OOM the
> live Reality/Hy2 inbounds and take paying users offline. Do **not** apply on
> the live node without headroom (post-upgrade or post-Remnawave migration), or
> an explicit accept-the-risk decision.

---

## 1. Choose the transport

### Option A — Trojan-TLS, direct, new port
- xray `trojan` inbound, `streamSettings.network=tcp`, `security=tls`, reuse the
  existing LE cert (`/etc/letsencrypt/live/<domain>/`, covers
  `144.172.101.217.sslip.io` + `sub.unlockvpn.site`).
- Pick a free TCP port (443/tcp = Reality, 8443 = nginx front, 8444 = subgw).
  e.g. **2087**.
- Simple, but a bare TLS listener on an odd port is weak against RU mobile DPI —
  adds little over VLESS Reality, which is the product's main job.

### Option B — Trojan-WS-TLS behind Cloudflare (recommended)
- Reuses the already-prepared `cdn.unlockvpn.site` **proxied/orange** record and
  reserved port 2083 (the "CDN protocol" task, item #4 in HANDOFF).
- xray `trojan` inbound, `network=ws`, `path=/<random>`, listen plaintext on
  127.0.0.1:<port>; Cloudflare terminates TLS, origin pulls via the proxied
  record. Traffic looks like normal HTTPS to a large CDN IP — strongest
  censorship resistance, best fit for the product.
- This is the same inbound the CDN task needs, so it does double duty.

## 2. Add the xray inbound (Marzban)

Edit `/var/lib/marzban/xray_config.json` on the node, add an inbound, then
`docker compose restart marzban` (US) / restart marzban-node (NL via panel).

Option A skeleton (fill cert paths + port):
```json
{
  "tag": "Trojan TLS",
  "listen": "0.0.0.0",
  "port": 2087,
  "protocol": "trojan",
  "settings": { "clients": [] },
  "streamSettings": {
    "network": "tcp",
    "security": "tls",
    "tlsSettings": {
      "certificates": [
        { "certificateFile": "/etc/letsencrypt/live/<domain>/fullchain.pem",
          "keyFile": "/etc/letsencrypt/live/<domain>/privkey.pem" }
      ]
    }
  },
  "sniffing": { "enabled": true, "destOverride": ["http", "tls"] }
}
```
Marzban manages `settings.clients` from the user DB — leave it empty here.

The inbound `tag` ("Trojan TLS") is what goes into `MARZBAN_DEFAULT_INBOUNDS`.

## 3. Grant users the Trojan proxy (bot `.env` on the bot-VPS)

On `23.95.3.18:/opt/vpn-bot/.env`:
```
MARZBAN_DEFAULT_PROXIES={"vless":{"flow":"xtls-rprx-vision"},"trojan":{}}
MARZBAN_DEFAULT_INBOUNDS={"vless":["VLESS Reality 443","VLESS Reality AMS"],"trojan":["Trojan TLS"]}
```
- `"trojan":{}` → Marzban auto-generates a per-user Trojan password.
- Premium lane uses `MARZBAN_REGION_INBOUNDS` instead — add the Trojan tag there
  per region to give premium users Trojan too.
- Re-sync: existing users gain Trojan on their next purchase/renewal (each calls
  `modify_user` with these defaults). New users get it immediately.
- `systemctl restart unlock-vpnbot` after editing.

## 4. Redeploy the gateway to the node

The gateway runs as `/opt/sub_gateway.py` on the US node. Push the updated file
and restart:
```
rsync -av services/sub_gateway.py root@144.172.101.217:/opt/sub_gateway.py   # via ~/.ssh/usnode, one ControlMaster conn
ssh -i ~/.ssh/usnode root@144.172.101.217 systemctl restart unlock-subgw
```

## 5. Verify

```
curl -s "$MARZBAN_BASE/sub/<token>" | base64 -d        # raw panel: trojan:// present
curl -s "https://sub.unlockvpn.site:8444/sub/<token>" | base64 -d   # gateway: trojan:// survives + Hy2 once/node
```
Then import the link in Happ — the location should list VLESS + Trojan +
Hysteria2. Watch node RAM (`free -m`) during/after the inbound restart.

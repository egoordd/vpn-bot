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

## Chosen transport: Trojan-WS behind Cloudflare (NL-targeted)

Decided 2026-06-27. Reuses the prepared `cdn.unlockvpn.site` **proxied/orange**
record. xray runs a **plaintext WS** trojan inbound (Cloudflare terminates TLS),
so it adds far less RAM than a TLS inbound — important given the US node has only
~43 MB free + 786 MB swap. Traffic looks like ordinary HTTPS to a large CDN IP:
strongest fit against RU mobile DPI. This is also the "CDN protocol" task (#4).

### Multi-node reality (read this first)
Marzban runs **one shared `xray_config.json`** (on the US panel,
`/var/lib/marzban/xray_config.json`) that the panel pushes to **every** connected
node. The NL marzban-node has **no shell** and is config-driven only. You cannot
make an inbound NL-exclusive in vanilla Marzban — it instantiates on US xray too.
NL targeting is done at the edge: point Cloudflare's `cdn` origin at the **NL IP
(107.189.22.160)** so all Trojan-WS traffic lands on NL; the US listener stays
idle. Current inbounds for reference: `VLESS Reality 443` (US :443),
`VLESS Reality AMS` (NL :2053, reality dest `107.189.22.160:8443`),
`Shadowsocks TCP` (:1080, unused).

### Two blockers before this can ship (why it's prepared, not applied)
1. **Cloudflare API token** is not stored (HANDOFF) — needed to set the `cdn`
   origin/port + SSL mode. Ask the user for it when ready.
2. Adding the inbound = edit the shared config on US + **restart marzban core**,
   which reloads US xray at ~43 MB free. Low-risk for a plaintext-WS inbound but
   still a brief prod touch on the protected node. Do it in a quiet window;
   `xray_config.json` backups already exist on the node to roll back.

## 2. Add the xray inbound (US panel `/var/lib/marzban/xray_config.json`)

Append to the `inbounds` array, keep a backup, then restart core. Plaintext WS,
no cert — Cloudflare does TLS:
```json
{
  "tag": "Trojan WS CDN",
  "listen": "0.0.0.0",
  "port": 2083,
  "protocol": "trojan",
  "settings": { "clients": [] },
  "streamSettings": {
    "network": "ws",
    "security": "none",
    "wsSettings": { "path": "/cdnws" }
  },
  "sniffing": { "enabled": true, "destOverride": ["http", "tls"] }
}
```
Marzban fills `settings.clients` from the user DB — leave it empty. Apply:
```
ssh -i ~/.ssh/usnode root@144.172.101.217   # one ControlMaster conn
cp /var/lib/marzban/xray_config.json /var/lib/marzban/xray_config.json.bak-trojan
# edit the file (append the inbound)
cd /opt/marzban && docker compose restart marzban   # reloads xray on US + pushes to NL
free -m   # confirm node survived
```

### Cloudflare side (needs the API token)
- `cdn.unlockvpn.site` **proxied**, origin → `107.189.22.160` (NL).
- Origin port 2083 is in Cloudflare's HTTPS-port set; since our origin is
  **plaintext**, either: (a) set SSL mode **Flexible** and use an HTTP origin
  port (80/8080/2052/2082/2086/2095) instead of 2083, or (b) keep 2083 + SSL
  **Full** and put a light TLS wrapper on origin. Prefer (a) for least RAM.
- The Trojan **Host** in Marzban (panel → inbound hosts) advertises
  `cdn.unlockvpn.site:443`, `host`/`sni`=`cdn.unlockvpn.site`, `path=/cdnws`,
  `security=tls`, so the client link points at Cloudflare, not the origin.

The inbound `tag` ("Trojan WS CDN") is what goes into `MARZBAN_DEFAULT_INBOUNDS`.

## 3. Grant users the Trojan proxy (bot `.env` on the bot-VPS)

On `23.95.3.18:/opt/vpn-bot/.env`:
```
MARZBAN_DEFAULT_PROXIES={"vless":{"flow":"xtls-rprx-vision"},"trojan":{}}
MARZBAN_DEFAULT_INBOUNDS={"vless":["VLESS Reality 443","VLESS Reality AMS"],"trojan":["Trojan WS CDN"]}
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

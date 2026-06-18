# Clean subscription URL via Cloudflare Tunnel

The subscription is served on a clean domain — `https://sub.unlockvpn.org/sub/<token>`
(no IP, no port) — instead of the IP-based `…sslip.io:8444`.

On the gateway node (`144.172.101.217`) port 443 is fully owned by Xray (VLESS
Reality), so we **can't** put the subscription on 443 there without touching the
live protocol. Instead a **Cloudflare Tunnel** fronts it: Cloudflare terminates
443 at the edge with its own cert and an outbound `cloudflared` connector
forwards to the local gateway. Reality is never touched.

```
client ──https://sub.unlockvpn.org──▶ Cloudflare edge ──QUIC tunnel──▶ cloudflared (node)
                                                                          └─▶ https://localhost:8444 (sub_gateway, noTLSVerify)
```

## Components

- **Domain:** `unlockvpn.org` registered at Namecheap, DNS on Cloudflare (Free).
  Nameservers: `jule.ns.cloudflare.com`, `michael.ns.cloudflare.com`.
- **Tunnel:** `unlock-sub`, id `e95c9403-7a16-41d4-9f6b-034b9654cf3b`
  (account-managed). Ingress: `sub.unlockvpn.org → https://localhost:8444`
  with `noTLSVerify: true` (gateway cert is for the sslip host, not the domain).
- **DNS:** `sub` CNAME → `<tunnel-id>.cfargotunnel.com`, proxied (orange cloud).
- **Connector:** `cloudflared` installed on the node from the official `.deb`,
  runs as the `cloudflared` systemd service (enabled, auto-starts on boot).
- **Bot:** `SUB_GATEWAY_URL=https://sub.unlockvpn.org` in `.env` — the bot rewrites
  every subscription link to this host (see `services.subscription.to_gateway_subscription_url`).

The legacy `…sslip.io:8444` gateway still runs, so links imported before the
switch keep working; new links the bot hands out use the clean domain.

## Recreate / manage

Tunnel + ingress + DNS were created via the Cloudflare API (needs a token with
`Account › Cloudflare Tunnel › Edit` + `Zone › DNS › Edit`). The API token is
**not** stored anywhere (transient, setup-only). The connector token lives only
in the node's cloudflared service config.

```sh
# node: connector status / logs
systemctl status cloudflared
journalctl -u cloudflared -n 50 --no-pager

# reinstall connector (token from CF dashboard: Zero Trust → Networks → Tunnels)
cloudflared service install <CONNECTOR_TOKEN>

# verify end-to-end
curl -sD - "https://sub.unlockvpn.org/sub/<token>" | grep -i profile-title
```

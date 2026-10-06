# AmneziaWG nodes

AmneziaWG = WireGuard + obfuscation (junk packets `Jc/Jmin/Jmax`, junk-prefixed
handshakes `S1/S2`, randomized magic headers `H1-H4`), so the traffic doesn't
carry WireGuard's recognizable fingerprint and survives DPI better than plain WG.

`setup-node.sh` installs it on an Ubuntu 24.04 node and brings up `awg0`
(idempotent). The obfuscation params in the script **must** match the bot's
`config.py` `AWG_*` defaults — the client configs the bot generates use those
same values, and a mismatch breaks the handshake.

## Live nodes

| Node | Endpoint | Tunnel subnet | Server public key |
|------|----------|---------------|-------------------|
| US | `144.172.101.217:51820` | `10.13.13.0/24` (clients `10.13.13.2+`) | `tpTvM9Vk7yz8u/f3whF66AcJKgvGXTXFX2zp1GzUMyU=` |
| NL | `107.189.22.160:51820` | `10.13.14.0/24` (clients `10.13.14.2+`) | `ZaHOMPke/MfJTBVcwqUCg80qIGcMJ+dtCv7FfhGcXnU=` |
| PL (routers) | `78.17.154.225:40001` | `10.13.15.0/24` (clients `10.13.15.2+`) | `syg9lBxe5gT1DGR0LCiIzja7OL+E/EBGuTPqG1LJ6Ag=` |
| PL (routers, RU mode) `awg1` | `78.17.154.225:40002` | `10.13.16.0/24` (clients `10.13.16.2+`) | `VNI7RQdp1Iz77XH6br7B81cmwaDgZ4B1GDmuoUtu80E=` |

The PL node (2026-10-06) serves hand-issued router files (Keenetic imports an
AmneziaWG `.conf` natively, no USB/Entware). It uses its own obfuscation
params, not the bot's defaults, so bot-provisioned peers would not handshake
there. Issue a client on the node with `awg-add-peer <name> 78.17.154.225`
(installed at `/usr/local/sbin/awg-add-peer`): it adds the peer live, appends
it to `awg0.conf` under a `# <name>` comment and prints the client `.conf`.
Revoke with `awg-del-peer <name> [iface]`.

`awg1` is the same with Russian services split off on the node (a router can't
split by site itself): its TCP is redirected into the `awg-ru` xray container
(`/opt/awg-ru`, `ru-split/setup-pl.sh`, config from `ru-split/gen_xray_config.py`
— the phone RU-mode lists), which sends Russian names and addresses through the
VK Cloud relay (key `relay-ru`, rule "all direct" → exits 212.233.122.241) and
everything else straight out of PL. If VK is down the balancer falls back to
the PL exit. QUIC (UDP 443) from `awg1` is rejected so apps fall back to TCP
and get split. Issue: `awg-add-peer <name> 78.17.154.225 awg1`.

Server private keys live only on the nodes at `/etc/amnezia/amneziawg/server_private.key`.

## What it touches (and doesn't)

- Adds a new `awg0` interface + a `MASQUERADE` rule scoped to the tunnel subnet
  + `FORWARD` accepts for `awg0`. Does **not** touch the existing Marzban/Xray
  (VLESS Reality :443) or Hysteria2 (:443/udp) services.
- `awg-quick@awg0` is enabled, so the tunnel comes back after reboot.

## Manage

```sh
awg show awg0                       # status, peers, handshakes
awg-quick down awg0 && awg-quick up awg0   # restart
awg set awg0 peer <PUBKEY> allowed-ips <IP>/32   # add a client peer (phase 2)
awg set awg0 peer <PUBKEY> remove                # revoke a client peer
```

## Validation method

Bring up a throwaway client elsewhere with `Table = off`, route a single target
through the tunnel, and confirm the egress IP/country:

```sh
ip route add 1.1.1.1/32 dev <client-iface>
curl -s https://1.1.1.1/cdn-cgi/trace | grep -E '^(ip|loc)='
```

`Table = off` + a single host route means the client's own routing/SSH is never
disturbed. Both nodes were confirmed this way (US -> loc=US, NL -> loc=NL).

## Provisioning key hardening

The bot provisions peers over SSH with a dedicated passphraseless key
(`~/.ssh/awg_provision` on the bot host). Because it's passphraseless root, the
key is locked to a forced command on each node so it can ONLY add/remove an
AmneziaWG peer within that node's subnet — nothing else.

Install `awg-provision-cmd` (this dir is a template; `__SUBNET_PREFIX__` is the
node's tunnel prefix, e.g. `10.13.13` on US, `10.13.14` on NL):

```sh
sed "s/__SUBNET_PREFIX__/10.13.13/" awg-provision-cmd | \
  ssh root@<node> "cat > /usr/local/sbin/awg-provision-cmd && chmod 755 /usr/local/sbin/awg-provision-cmd"
```

Then prefix the awg-provision key line in the node's `~/.ssh/authorized_keys`
(leave other keys untouched):

```
command="/usr/local/sbin/awg-provision-cmd",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... awg-provision@vpn-bot
```

The wrapper only accepts the exact commands `services/awg_provision.py` sends
(`awg set awg0 peer '<pub>' allowed-ips <ip>/32 && awg-quick save awg0` and the
`remove` form), validating the pubkey shape and that the IP is inside the node's
subnet. Verified: arbitrary commands (`id`, `cat /etc/shadow`) are rejected;
provision/revoke still work.

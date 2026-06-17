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

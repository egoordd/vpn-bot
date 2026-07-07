# VPN egress abuse filter

Blocks outbound `22` (SSH), `3389` (RDP) and `5432` (PostgreSQL) from VPN data
nodes so the shared exit IP can't be used to brute-force / scan those services.
Own infra IPs stay reachable, so node↔panel management is unaffected.

All VPN containers run `net=host`, so egress goes through the host `OUTPUT`
chain; `FORWARD` is also covered for WireGuard/AmneziaWG. The systemd unit runs
`After=ufw.service docker.service` and inserts its jump first, so it survives
`ufw reload` and reboots. The script is idempotent.

## Install on a node

```
install -m 0755 vpn-egress-block.sh /usr/local/sbin/vpn-egress-block.sh
install -m 0644 vpn-egress-block.service /etc/systemd/system/vpn-egress-block.service
systemctl daemon-reload
systemctl enable --now vpn-egress-block.service
```

## Verify

```
# node itself must not reach an external SSH port, but 443 must work
timeout 6 bash -c '</dev/tcp/140.82.121.3/22' && echo OPEN || echo REJECTED   # want REJECTED
timeout 6 bash -c '</dev/tcp/140.82.121.3/443' && echo OPEN || echo blocked   # want OPEN
iptables -L VPN_EGRESS_BLOCK -nv --line-numbers
```

## Applied on

- US `144.172.101.217` — 2026-07-07
- PL `78.17.154.225` — 2026-07-07
- NL `107.189.22.160` — pending (no shell access yet)

## Tuning

Add ports to `PORTS` in the script (e.g. `25,465,587` to also stop outbound
spam) and re-run the unit. To exempt an additional host, add it to `INFRA`.

#!/bin/sh
# Anti-abuse egress filter for VPN data nodes.
#
# Stops VPN clients (and the node itself) from opening OUTBOUND connections to
# common service ports, so the node's IP cannot be used to brute-force / scan
# SSH(22), RDP(3389) or PostgreSQL(5432) elsewhere. Without this, one abusive
# user gets the shared exit IP onto blocklists and triggers abuse complaints.
#
# All VPN containers run net=host, so their egress is the host OUTPUT chain;
# FORWARD is covered too for any WireGuard/AmneziaWG routed traffic. Our own
# infra IPs stay reachable so node<->panel management is never affected.
#
# Idempotent. Installed as a systemd oneshot (vpn-egress-block.service) that
# runs After=ufw.service docker.service so its jumps sit first in OUTPUT/FORWARD.
set -e

CHAIN=VPN_EGRESS_BLOCK
PORTS=22,3389,5432
INFRA="23.95.3.18 144.172.101.217 78.17.154.225 107.189.22.160"

apply() {
  ipt="$1"
  $ipt -N "$CHAIN" 2>/dev/null || $ipt -F "$CHAIN"
  $ipt -A "$CHAIN" -o lo -j RETURN
  if [ "$ipt" = "iptables" ]; then
    for ip in $INFRA; do $ipt -A "$CHAIN" -d "$ip" -j RETURN; done
  fi
  $ipt -A "$CHAIN" -p tcp -m multiport --dports "$PORTS" -j REJECT --reject-with tcp-reset
  $ipt -C OUTPUT  -j "$CHAIN" 2>/dev/null || $ipt -I OUTPUT  1 -j "$CHAIN"
  $ipt -C FORWARD -j "$CHAIN" 2>/dev/null || $ipt -I FORWARD 1 -j "$CHAIN"
}

apply iptables
apply ip6tables 2>/dev/null || true

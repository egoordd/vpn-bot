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

---

# unlock-egress-guard — защита от исходящего сканирования (09.10.2026)

Причина: хостер удалил старый немецкий сервер 166.0.28.132 по жалобе — 07.10 с
него сканировали порты чужих серверов (SYN с исходным портом 61000: пример из
инструкции masscan, то есть скорее всего был взлом с root, а не клиент VPN).

Два слоя, подробности — в шапке скрипта:

- **iptables** (OUTPUT + пересылка с `awg+ wg+ docker0 br-+`, при docker — в
  `DOCKER-USER`): SYN с исходного порта 61000+ с самого сервера; >50/с к одному
  адресу на «редкие» порты; >100/с на один «редкий» порт; >200/с к одному адресу.
  «Редкие» = всё, кроме 80,443,853,5222,5223,5228,4244,5242. Наши серверы и
  частные сети не считаются. Это про злоупотребления клиентов VPN.
- **tc egress** на основном интерфейсе: SYN с исходного порта 61000+ режется и
  у кадров, собранных в обход ядра (masscan шлёт через AF_PACKET мимо iptables).
  Не ставится там, где есть туннели AWG/WG: роутеры клиентов законно ходят с
  портов 61000+.

Таймер `unlock-egress-guard-check.timer` раз в 5 минут возвращает правила, если
их сбросили ufw/docker. Срабатывания — в журнале ядра: `journalctl -k | grep unlock-egress`.

## Установка/обновление на узле

```
install -m 0755 unlock-egress-guard /usr/local/sbin/unlock-egress-guard
install -m 0644 unlock-egress-guard.service unlock-egress-guard-check.service unlock-egress-guard-check.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable unlock-egress-guard.service unlock-egress-guard-check.timer
systemctl restart unlock-egress-guard.service
systemctl start unlock-egress-guard-check.timer
unlock-egress-guard status
```

Выключить: `systemctl disable --now unlock-egress-guard-check.timer unlock-egress-guard.service`.
Копия правил до установки — `/root/egress-guard-backup/`.

Новый наш сервер — добавить его адрес в `INFRA4` в скрипте и раскатать заново,
иначе каскады к нему попадут под лимиты.

## Где стоит (09.10.2026)

США-2, Литва, Германия 178.17.58.232, FI-1/2/3, NL-корп, ind-DE, московский
релей, VK-фронт 212.233.122.241 — оба слоя. Польша, Нидерланды 107.189.22.160 —
только iptables (есть AWG). Пороги проверены в отдельном сетевом пространстве:
скан 2000 портов → прошло 202, 5222/443 не тронуты.

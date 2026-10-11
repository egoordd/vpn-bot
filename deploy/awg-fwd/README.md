# Вход AmneziaWG через российский адрес

Для клиентов, у которых провайдер режет WireGuard/AmneziaWG за границу. 11.10.2026:
Ростелеком (Якутск, AS12389) — с роутера клиента на польский вход не доходило ни одного
пакета. Через российский адрес провайдер пакеты пропускает, а дальше они идут в Польшу
из дата-центра.

Схема: клиент → `168.113.211.89:40002/udp` (доп. адрес сервера сайта 168.113.210.6) →
DNAT/SNAT → `78.17.154.225:40002/udp` (PL, `awg1`, РУ-режим). Ключи и параметры
маскировки те же, у клиента меняется только `Endpoint`.

VK-фронт 212.233.122.241 для этого не годится: облако VK пропускает внутрь только TCP.

## Установка (сервер сайта)

```bash
install -m 755 unlock-awg-fwd /usr/local/sbin/unlock-awg-fwd
install -m 644 unlock-awg-fwd.service /etc/systemd/system/unlock-awg-fwd.service
printf "net.ipv4.ip_forward = 1\n" > /etc/sysctl.d/90-unlock-awg-fwd.conf
ufw route allow proto udp from any to 78.17.154.225 port 40002 comment "awg fwd 168.113.211.89 -> PL awg1"
systemctl daemon-reload && systemctl enable --now unlock-awg-fwd
```

Снять: `systemctl disable --now unlock-awg-fwd` и `ufw route delete allow proto udp from any to 78.17.154.225 port 40002`.

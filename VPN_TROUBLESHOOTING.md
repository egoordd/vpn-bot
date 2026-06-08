# Решение: VPN подключается, но интернет не работает

Подробный разбор почему WireGuard-сервер был запущен и принимал handshake, но трафик пользователей в интернет не уходил.

---

## Симптомы

- ✅ WireGuard сервер запущен (`systemctl status wg-quick@wg0` — active)
- ✅ Бот выдаёт корректный конфиг и QR-код
- ✅ Клиент успешно подключается к VPN
- ✅ `wg show` показывает `latest handshake: X seconds ago`
- ❌ Интернет на устройстве **не работает**: сайты не открываются, Telegram молчит, всё висит
- ❌ Любое приложение/браузер не получает ответа

Со стороны клиента — выглядит как будто VPN "висит".

---

## Диагностика — две корневые причины

### Причина 1: Конфликт IP-подсетей

Когда ставишь WireGuard на VPS, важно проверить какую подсеть использует **сам сервер** для своей внешней сети.

**Команда диагностики:**
```bash
ip route | grep default
```

**Что увидел:**
```
default via 10.0.0.1 dev net0 proto static
```

**Проблема:** Внешний шлюз сервера — `10.0.0.1`, то есть провайдер (Aeza) использует подсеть `10.0.0.0/24` для своей внутренней сети между виртуалками.

А мы настроили WireGuard на той же самой подсети `10.0.0.0/24` (с адресом `10.0.0.1/24` для wg0).

**Что происходит:**
- Клиент получает IP `10.0.0.2` от VPN
- Сервер не знает, куда роутить эти пакеты — они конфликтуют с его собственной внешней сетью
- Пакеты теряются между интерфейсами `wg0` и `net0`

**Аналогия:** Как если бы у тебя в офисе IP-адрес `192.168.1.5`, и ты приходишь домой, где роутер тоже выдал тебе `192.168.1.5`. Сетевая карта не знает, в какую сторону отправлять пакет.

### Причина 2: iptables FORWARD chain не пропускал возвратный трафик

Политика FORWARD по умолчанию `DROP`. Изначально мы добавили правило:

```bash
iptables -A FORWARD -i wg0 -j ACCEPT
```

Это разрешает только пакеты **входящие в wg0** (от клиента к серверу), но **не разрешает возвратные пакеты** (от интернета через сервер обратно к клиенту).

**Команда диагностики:**
```bash
iptables -L FORWARD -v -n
```

**Что увидел:**
```
Chain FORWARD (policy DROP 2594 packets, 378K bytes)
 pkts bytes target     prot opt in     out     source        destination
 4502 559K DOCKER-USER all  --  *      *       0.0.0.0/0     0.0.0.0/0
 4502 559K DOCKER-FORWARD all -- *     *       0.0.0.0/0     0.0.0.0/0
 1756 125K ACCEPT      all  --  wg0    *       0.0.0.0/0     0.0.0.0/0
```

- `1756` пакетов прошли (от клиента к серверу через wg0)
- `2594` пакетов дропнуто (ответные пакеты от интернета, которые сервер пытался отправить клиенту)

**Что подтверждает диагноз** — `wg show`:
```
peer: +nMDIel4mBEiKigQ47PE66JWuhhwT6BgEWDflqWV3mM=
  endpoint: 128.71.18.86:53914
  allowed ips: 10.8.0.2/32
  latest handshake: 6 seconds ago
  transfer: 47.52 KiB received, 376 B sent  ⬅️ КЛЮЧ!
```

Клиент шлёт сервер 47 KiB, а сервер отвечает только 376 байт. **Это значит handshake работает, но реальные данные не возвращаются клиенту.**

---

## Решение

### Шаг 1. Сменить подсеть WireGuard на не-конфликтующую

Выбрал `10.8.0.0/24` (стандартная для WireGuard, не пересекается с типовыми сетями VPS).

```bash
# Остановить WireGuard
systemctl stop wg-quick@wg0

# Сменить IP сервера в конфиге
sed -i 's|10.0.0.1/24|10.8.0.1/24|' /etc/wireguard/wg0.conf

# Запустить обратно
systemctl start wg-quick@wg0
```

Также сменить пул IP-адресов для клиентов в `.env` бота:

```bash
sed -i 's|10.0.0.0/24|10.8.0.0/24|' ~/vpn-bot/.env
```

### Шаг 2. Очистить старые ключи и peer'ов

Старые конфиги из БД содержат IP из старой подсети (`10.0.0.x`):

```bash
# Очистить таблицу wireguard_keys
docker compose exec postgres psql -U vpn_bot -d vpn_bot -c "DELETE FROM wireguard_keys;"

# Снять всех peer'ов с работающего WireGuard
wg show wg0 peers | xargs -I {} wg set wg0 peer {} remove

# Удалить старые конфиг-файлы
rm -rf /etc/wireguard/clients/*

# Пересоздать контейнер бота чтобы он подхватил новый .env
docker compose up -d --force-recreate bot
```

После этого `/test_key` (или покупка) выдаст новый конфиг с IP `10.8.0.x`.

### Шаг 3. Разрешить возвратный трафик в FORWARD

Добавить правило ACCEPT для пакетов **исходящих в wg0** (от интернета обратно к клиенту):

```bash
iptables -I FORWARD -o wg0 -j ACCEPT
```

VPN заработал **сразу** после этого правила.

### Шаг 4. Закрепить правила навсегда (чтобы пережили перезагрузку)

Обновить `PostUp`/`PostDown` в `/etc/wireguard/wg0.conf`:

```bash
sed -i 's|PostUp = iptables -A FORWARD -i wg0 -j ACCEPT|PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT|' /etc/wireguard/wg0.conf

sed -i 's|PostDown = iptables -D FORWARD -i wg0 -j ACCEPT|PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT|' /etc/wireguard/wg0.conf
```

---

## Финальный рабочий `/etc/wireguard/wg0.conf`

```ini
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = <твой_приватный_ключ_сервера>
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o net0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o net0 -j MASQUERADE
```

Где:
- `Address = 10.8.0.1/24` — нерасходящаяся с провайдером подсеть
- `iptables -A FORWARD -i wg0 -j ACCEPT` — пакеты от клиента в интернет
- `iptables -A FORWARD -o wg0 -j ACCEPT` — пакеты из интернета обратно клиенту
- `iptables -t nat -A POSTROUTING -o net0 -j MASQUERADE` — NAT/маскарад (подмена IP клиента на IP сервера)

---

## Проверочный чек-лист

Если VPN не работает — пройти по списку:

```bash
# 1. WireGuard запущен?
systemctl status wg-quick@wg0

# 2. IP forwarding включён?
sysctl net.ipv4.ip_forward
# Должно быть: net.ipv4.ip_forward = 1

# 3. Подсеть WireGuard НЕ конфликтует с внешней сетью?
ip route | grep default
ip addr show wg0
# IP сетей не должны пересекаться

# 4. Handshake происходит?
wg show
# Должно быть: latest handshake: N seconds ago

# 5. Трафик симметричный? (если нет — проблема в FORWARD/NAT)
wg show
# transfer: X received, Y sent — X и Y примерно одного порядка

# 6. FORWARD chain пропускает в обе стороны?
iptables -L FORWARD -v -n
# Должны быть ACCEPT для wg0 в IN и OUT, или ESTABLISHED,RELATED ACCEPT

# 7. MASQUERADE настроен?
iptables -t nat -L POSTROUTING -v -n
# Должно быть MASQUERADE для исходящего интерфейса (обычно net0/eth0/ens3)

# 8. Имя внешнего интерфейса в MASQUERADE правильное?
ip route | grep default
# Сравни имя dev (net0/eth0) с тем что в PostUp wg0.conf
```

---

## Почему это так часто ломается у новичков

1. **Дефолтная подсеть в туториалах** часто `10.0.0.0/24` — она же популярна у провайдеров для внутренней сети VPS. Конфликт неизбежен.

2. **iptables правила** в большинстве туториалов даны только для одного направления (`-i wg0`). Работает на серверах где FORWARD policy = ACCEPT (некоторые дистрибутивы). Не работает на серверах с DROP (Ubuntu Server, после установки Docker и пр.).

3. **Docker меняет iptables** — после `docker compose up` появляются цепочки `DOCKER-USER`, `DOCKER-FORWARD`, и политика FORWARD = DROP. Если WireGuard был настроен до Docker'а — он внезапно перестаёт работать после установки Docker.

4. **Нет очевидной ошибки** — `wg show` показывает успешный handshake, `systemctl status` показывает active. Кажется что всё работает, но трафик молча дропается на iptables.

---

## TL;DR

```bash
# 1. Сменить подсеть на 10.8.0.0/24 (не 10.0.0.0/24!)
# 2. Добавить ОБА правила:
iptables -A FORWARD -i wg0 -j ACCEPT
iptables -A FORWARD -o wg0 -j ACCEPT
# 3. MASQUERADE на правильный внешний интерфейс:
iptables -t nat -A POSTROUTING -o $(ip route | awk '/default/ {print $5}') -j MASQUERADE
```

Это решает 99% случаев "VPN подключается, но интернета нет".

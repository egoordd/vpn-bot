# Деплой UnLock VPN на новый сервер Aeza

> Пошаговый чеклист с командами. Делай по порядку, ничего не пропускай.

---

## ЭТАП 0: Заказ сервера

### Параметры:
- **Провайдер:** Aeza (https://aeza.net)
- **Локация:** Amsterdam, Нидерланды
- **ОС:** Ubuntu 24.04 LTS (или 26.04 если есть)
- **Тариф:** минимум 1 vCPU / 1 GB RAM / 25 GB SSD / 200 Мбит/с
- **Оплата:** **МЕСЯЧНАЯ** (не почасовая!), включить автопродление чтобы не удалили

### После создания сохрани:
```
IP сервера: ________________
root password: ________________
SSH порт: 22 (если не указано иное)
```

---

## ЭТАП 1: Доступ к серверу

Через **VNC-консоль в панели Aeza** (т.к. они блокируют SSH 22 снаружи):
1. Зайди в панель → нажми на сервер → "Консоль" / "VNC"
2. Логинься: `root` + пароль

> ⚠️ Если VNC не работает — попробуй заказать у Aeza смену порта SSH или поддержка.

---

## ЭТАП 2: Базовая настройка системы

```bash
# Обновление
apt update && apt upgrade -y

# Установка нужного
apt install -y curl git wireguard iptables-persistent ufw qrencode

# DNS (важно — без этого Docker не сможет качать образы)
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 1.1.1.1" >> /etc/resolv.conf

# Docker
curl -fsSL https://get.docker.com | sh

# Включить ip forwarding
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p
```

---

## ЭТАП 3: WireGuard ключи и конфиг

### Сгенерировать ключи сервера:
```bash
cd /etc/wireguard
wg genkey | tee server_private.key | wg pubkey > server_public.key
chmod 600 server_private.key
SERVER_PRIVATE=$(cat server_private.key)
SERVER_PUBLIC=$(cat server_public.key)
echo "PRIVATE: $SERVER_PRIVATE"
echo "PUBLIC:  $SERVER_PUBLIC"
```

**Сохрани `PUBLIC` — пойдёт в `.env` как `WG_SERVER_PUBLIC_KEY`.**

### Узнать имя внешнего интерфейса (обычно `eth0` или `net0`):
```bash
ip route | grep default
# Например: "default via 10.0.0.1 dev net0" → интерфейс net0
```

### Создать `/etc/wireguard/wg0.conf`:
```bash
INTERFACE_NAME=net0  # ← подставь своё значение!

cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.8.0.1/24
ListenPort = 51820
PrivateKey = $(cat /etc/wireguard/server_private.key)

PostUp = iptables -A FORWARD -i wg0 -j ACCEPT
PostUp = iptables -I FORWARD -o wg0 -j ACCEPT
PostUp = iptables -t nat -A POSTROUTING -o ${INTERFACE_NAME} -j MASQUERADE

PostDown = iptables -D FORWARD -i wg0 -j ACCEPT
PostDown = iptables -D FORWARD -o wg0 -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -o ${INTERFACE_NAME} -j MASQUERADE
EOF

# Запустить
systemctl enable --now wg-quick@wg0
wg show  # должен показать interface wg0
```

---

## ЭТАП 4: Файрвол (UFW)

```bash
ufw allow 22/tcp        # SSH (если работает)
ufw allow 51820/udp     # WireGuard
ufw --force enable
ufw status
```

---

## ЭТАП 5: Docker DNS

```bash
cat > /etc/docker/daemon.json <<EOF
{
  "dns": ["8.8.8.8", "1.1.1.1"],
  "mtu": 1420
}
EOF
systemctl restart docker
```

---

## ЭТАП 6: Клонирование бота

```bash
cd /root
git clone https://github.com/egoordd/vpn-bot.git
cd vpn-bot
```

---

## ЭТАП 7: Создание `.env`

⚠️ **НЕ копируй пароли с экрана — введи их вручную через `nano`**.

```bash
nano .env
```

Содержимое — подставь свои значения:

```env
# Telegram
BOT_TOKEN=ТУТ_ТВОЙ_ТОКЕН_БОТА_ОТ_BOTFATHER
ADMIN_IDS=ТВОЙ_TELEGRAM_USER_ID
SUPPORT_USERNAME=твой_username_без_собаки

# CryptoBot (получил из @CryptoBot → Crypto Pay → Create App)
CRYPTOBOT_TOKEN=ТУТ_ТОКЕН_ОТ_CRYPTOBOT
CRYPTOBOT_API_URL=https://pay.crypt.bot/api
CRYPTOBOT_POLL_INTERVAL=30

# WireGuard
WG_INTERFACE=wg0
WG_SERVER_PUBLIC_KEY=ТУТ_PUBLIC_KEY_СЕРВЕРА_ИЗ_ЭТАПА_3
WG_SERVER_ENDPOINT=IP_СЕРВЕРА:51820
WG_CLIENT_DNS=1.1.1.1
WG_ALLOWED_IPS=0.0.0.0/0, ::/0
WG_CLIENT_ADDRESS_POOL=10.8.0.0/24
WG_CONFIG_PATH=/etc/wireguard/clients

# Database
DATABASE_URL=postgresql+asyncpg://vpn_bot:vpn_bot_password@localhost:5432/vpn_bot

# Redis
REDIS_URL=redis://localhost:6379/0

DB_ECHO=false
```

Сохрани: `Ctrl+O` → `Enter` → `Ctrl+X`.

### Проверка:
```bash
cat .env | grep -E "BOT_TOKEN|CRYPTOBOT_TOKEN|WG_SERVER" 
# Все три должны быть заполнены
```

---

## ЭТАП 8: Папка для клиентских конфигов

```bash
mkdir -p /etc/wireguard/clients
chmod 700 /etc/wireguard/clients
```

---

## ЭТАП 9: Запуск Docker Compose

```bash
cd /root/vpn-bot
docker compose up -d --build
```

Подождать ~30 секунд, проверить:
```bash
docker compose ps
# Должно быть 3 контейнера UP: bot, postgres, redis

docker compose logs -f bot
# Должны увидеть "Bot started" и polling сообщения
# Ctrl+C чтобы выйти из логов (бот продолжит работать)
```

---

## ЭТАП 10: Тестирование

### 10.1. /start
- Открыть бота в Telegram
- Нажать `/start`
- **Ожидать:** баннер UnLock + 3 кнопки тарифа (149₽/399₽/699₽)

### 10.2. Админский /test_key
- Отправить боту `/test_key` (от твоего аккаунта — должен быть в ADMIN_IDS)
- **Ожидать:** Подписка активирована + .conf файл + QR

### 10.3. Подключение VPN
- Скачать WireGuard на телефон
- Импортировать конфиг (через QR или .conf)
- Включить туннель
- Проверить IP: https://2ip.ru — должен показать Amsterdam

### 10.4. Проверка трафика
```bash
wg show
# Должны быть:
# - peer (твой публичный ключ)
# - latest handshake: несколько секунд назад
# - transfer: байты в обе стороны (не 0!)
```

### 10.5. Тестовая оплата CryptoBot
- В боте нажать "30 дней — 149₽"
- Должна прийти кнопка "🔓 Оплатить — 1.99 USDT"
- Перейти, оплатить тестовыми $1.99 (или попросить тест-аккаунт CryptoBot)
- **В течение 30 секунд** должен прийти конфиг + QR + инструкция

---

## ЭТАП 11: Дополнительная защита

### Бэкап БД (раз в день, cron):
```bash
crontab -e
# Добавь строку:
0 3 * * * cd /root/vpn-bot && docker compose exec -T postgres pg_dump -U vpn_bot vpn_bot | gzip > /root/backups/db-$(date +\%Y\%m\%d).sql.gz

mkdir -p /root/backups
```

### Авторестарт бота при падении:
В `docker-compose.yml` для сервиса `bot` уже должно быть `restart: unless-stopped` — проверь:
```bash
grep -A 1 "restart:" /root/vpn-bot/docker-compose.yml
```

---

## Что делать если что-то пошло не так

### Бот не стартует
```bash
docker compose logs bot --tail 100
```
Типичные ошибки:
- `pydantic ValidationError` → ошибка в `.env` (что-то не заполнено)
- `ImportError` → код не до конца обновлён, делай `git pull && docker compose up -d --build`
- `Connection refused` к postgres → подожди 10 сек, postgres стартует медленнее

### VPN подключается, но нет интернета
```bash
# 1. Проверь ip_forward
sysctl net.ipv4.ip_forward  # должно быть = 1

# 2. Проверь FORWARD правила
iptables -L FORWARD -v -n
# Должны быть две строки ACCEPT для wg0 (i и o)

# 3. Проверь NAT
iptables -t nat -L POSTROUTING -v -n
# Должна быть MASQUERADE для wg0
```

### CryptoBot не доставляет ключ после оплаты
```bash
docker compose logs bot | grep -i cryptobot
# Должны быть периодические сообщения "polling cryptobot..."
# Если нет → scheduler не запущен или CRYPTOBOT_TOKEN пустой
```

---

## Контрольный список перед "запуском в прод"

- [ ] Сервер заказан, месячный тариф, автопродление ON
- [ ] WireGuard работает, `wg show` показывает interface
- [ ] `.env` заполнен полностью (BOT_TOKEN, CRYPTOBOT_TOKEN, WG_*, ADMIN_IDS)
- [ ] Docker compose стартует все 3 контейнера
- [ ] `/start` показывает баннер + тарифы
- [ ] `/test_key` выдаёт рабочий конфиг
- [ ] VPN-туннель пропускает трафик (handshake + transfer ≠ 0)
- [ ] Тестовая CryptoBot-оплата прошла через polling
- [ ] Бэкапы БД настроены в cron
- [ ] UFW разрешает только 22/tcp и 51820/udp

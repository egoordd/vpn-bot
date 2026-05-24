# VPN Bot MVP

MVP Telegram-бота для продажи VPN-доступа по подписке через Telegram Stars.

## Что внутри

- aiogram 3.x с FSM для покупки
- PostgreSQL + SQLAlchemy async
- Redis FSM storage
- WireGuard CLI через `wg`
- Telegram Payments / Stars
- QR-коды WireGuard-конфига
- APScheduler для напоминаний и отключения истекших подписок
- Docker Compose для запуска бота, PostgreSQL и Redis

## Подготовка WireGuard

На сервере должен быть установлен и запущен WireGuard-интерфейс, например `wg0`.

Минимальный пример серверного `/etc/wireguard/wg0.conf`:

```ini
[Interface]
Address = 10.0.0.1/24
ListenPort = 51820
PrivateKey = SERVER_PRIVATE_KEY
PostUp = sysctl -w net.ipv4.ip_forward=1
```

Запуск:

```bash
sudo apt-get update
sudo apt-get install -y wireguard
sudo systemctl enable --now wg-quick@wg0
sudo wg show wg0 public-key
```

Публичный ключ сервера нужно указать в `WG_SERVER_PUBLIC_KEY`.

## Настройка

```bash
cd ~/vpn-bot
cp .env.example .env
```

Заполните `.env`:

- `BOT_TOKEN` - токен бота от `@BotFather`
- `PAYMENT_TOKEN` - для Telegram Stars оставьте пустым
- `WG_SERVER_PUBLIC_KEY` - публичный ключ сервера WireGuard
- `WG_SERVER_ENDPOINT` - IP/домен сервера и порт, например `1.2.3.4:51820`
- `SUPPORT_USERNAME` - контакт поддержки
- `ADMIN_IDS` - Telegram ID администраторов через запятую

## Запуск

```bash
docker-compose up -d --build
docker-compose logs -f bot
```

Бот сам создаст таблицы при старте.

## Как бот добавляет клиентов WireGuard

После успешной оплаты бот:

1. генерирует приватный и публичный ключ клиента через `wg genkey` и `wg pubkey`;
2. выбирает свободный IP из `WG_CLIENT_ADDRESS_POOL`, начиная с `10.0.0.2`;
3. создает клиентский `.conf` в `WG_CONFIG_PATH`;
4. добавляет peer командой:

```bash
wg set wg0 peer CLIENT_PUBLIC_KEY allowed-ips CLIENT_IP/32
```

Docker Compose монтирует `/etc/wireguard` и добавляет `NET_ADMIN`. Если WireGuard-интерфейс находится не в network namespace контейнера, запускайте бота на том же хосте/namespace, где доступна команда `wg set wg0`, либо адаптируйте compose под вашу схему деплоя.

## Проверка

После старта отправьте боту `/start`, выберите «Купить VPN», оплатите invoice в Stars, затем бот пришлет `.conf` файл и QR-код.

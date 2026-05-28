# ТЗ: VPN-бот "UnLock" — UX-редизайн + CryptoBot

> **Контекст:** Существующий VPN-бот на aiogram 3 + PostgreSQL + Redis + WireGuard работает на VPS Aeza (79.137.204.79). Сейчас оплата только через Telegram Stars. Цель — превратить его в массовый продукт в стиле HitVPN / Молния VPN.

---

## Что делаем

### 1. Полностью убрать Telegram Stars
Stars удаляются как способ оплаты. Весь связанный код (`send_invoice`, `pre_checkout_query`, `successful_payment_handler` в `bot/handlers/buy.py`, использование `PAYMENT_TOKEN`) выпиливается.

**Что оставить:** хендлер `/test_key` в `bot/handlers/admin.py` — там нет Stars-логики, только генерация конфига для тестов.

### 2. Добавить CryptoBot как единственный платёжный шлюз
- API base: `https://pay.crypt.bot/api`
- Auth: HTTP-заголовок `Crypto-Pay-API-Token: <CRYPTOBOT_TOKEN>`
- Активы: USDT (приоритет), TON, BTC, ETH (CryptoBot сам показывает выбор внутри)
- Документация: https://help.crypt.bot/crypto-pay-api

### 3. Ребрендинг — название "UnLock"
Везде в текстах сменить "VPN Bot" → "UnLock". Слоган: **"Быстрый VPN за копейки"**.

---

## Цены (финальные)

| Тариф | Дней | Цена ₽ | Цена USDT (для CryptoBot) |
|-------|------|--------|---------------------------|
| 🚀 Старт | 30 | 149₽ | 1.99 |
| 💎 Стандарт | 90 | 399₽ | 4.99 |
| 👑 Полугодовой | 180 | 699₽ | 7.99 |

В кнопках UI показываем **рубли** (как основной "понятный" прайс), при оплате через CryptoBot инвойс выставляется в USDT.

---

## Архитектура изменений

### 3.1. `config.py`
Добавить поля:
```python
CRYPTOBOT_TOKEN: str = ""
CRYPTOBOT_API_URL: str = "https://pay.crypt.bot/api"
CRYPTOBOT_POLL_INTERVAL: int = 30  # секунд
```

Можно убрать `PAYMENT_TOKEN` (он был для Stars).

### 3.2. `services/cryptobot.py` (новый файл)
Клиент CryptoBot API через `aiohttp`:

```python
async def create_invoice(amount: str, payload: str, description: str, asset: str = "USDT", expires_in: int = 3600) -> dict
async def get_invoices_by_status(status: str = "paid", count: int = 100) -> list[dict]
async def get_invoice_by_id(invoice_id: int) -> dict | None
```

**Формат payload:** `unlock:{user_id}:{plan}:{uuid4_hex}` — чтобы при доставке ключа знать, кому и какой тариф активировать.

**Возвращает CryptoBot:** объект с `invoice_id`, `status`, `amount`, `asset`, `pay_url`, `bot_invoice_url`, `mini_app_invoice_url`, `payload`, ...

### 3.3. `database/models.py` — таблица `Payment`
Добавить колонки (миграция через `Base.metadata.create_all` сработает для новых полей, но **существующая БД на проде потребует ручного `ALTER TABLE`** или дроп таблицы — обсудить с админом):

```python
provider: Mapped[str] = mapped_column(String(32), default="cryptobot")  # "cryptobot" | "telegram_stars" (legacy)
external_invoice_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
```

И индекс на `external_invoice_id` для быстрого поиска.

В `repository.py` добавить:
- `create_cryptobot_payment(user_id, amount, external_invoice_id, invoice_payload, plan)` 
- `get_payment_by_external_id(external_invoice_id) -> Payment | None`
- `complete_payment_by_external_id(external_invoice_id) -> Payment | None`

### 3.4. `scheduler/tasks.py` — новая джоба `poll_cryptobot_payments`
Запускается каждые 30 секунд (из `CRYPTOBOT_POLL_INTERVAL`):

1. Вызывает `get_invoices_by_status("paid", count=100)` — получает все оплаченные инвойсы
2. Для каждого инвойса:
   - Парсит `payload` → достаёт `user_id`, `plan`, `uuid`
   - Ищет в БД `payment` по `external_invoice_id`
   - Если уже `completed` — пропускает (идемпотентность)
   - Если `pending` — помечает `completed`, активирует подписку через `services.subscription.activate_subscription`, генерит/получает WireGuard-конфиг через `services.wireguard.ensure_user_peer`
   - Отправляет пользователю сообщение с ключом (см. ниже формат)

**Важно:** джоба идемпотентна — повторный запуск не создаст дубль подписки и не отправит ключ дважды.

### 3.5. UX-редизайн

#### `bot/handlers/start.py` — умный welcome
```python
@router.message(CommandStart())
async def start_handler(...):
    # 1. Загрузить/создать пользователя
    # 2. Проверить активную подписку через repo.get_active_subscription(user_id)
    # 3a. Если есть → active_subscription_keyboard + текст со статусом
    # 3b. Если нет → landing_keyboard + маркетинговый текст
    # 4. Прислать сообщение с баннером (assets/banner.png) через answer_photo
```

#### `bot/keyboards/main_menu.py` — две функции
```python
def landing_keyboard() -> InlineKeyboardMarkup:
    # 🚀 30 дней — 149₽   → callback "buy:1m"
    # 💎 90 дней — 399₽   → callback "buy:3m"  
    # 👑 180 дней — 699₽  → callback "buy:6m"
    # ❓ Поддержка        → callback "support"
    # 📖 Инструкция       → callback "instructions"

def active_subscription_keyboard() -> InlineKeyboardMarkup:
    # 📱 Получить ключ    → callback "get_key"
    # 🔄 Продлить         → callback "buy_menu"  (показывает тарифы)
    # ❓ Поддержка        → callback "support"

def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    # ◀️ В меню → callback "main_menu"
```

#### `bot/handlers/buy.py` — полный рерайт
Флоу:
1. **Callback `buy:{plan}`** → создаёт CryptoBot-инвойс через `services.cryptobot.create_invoice`
   - Сохраняет `payment` в БД с `provider="cryptobot"`, `external_invoice_id=<id>`, `status="pending"`
   - Отправляет пользователю сообщение:
     ```
     💳 Оплата тарифа: 30 дней — 149₽
     
     Нажми кнопку ниже, выбери валюту (USDT/TON/BTC) и оплати.
     Ключ придёт автоматически в течение минуты после оплаты.
     ```
     С inline-кнопкой:
     - `🔓 Оплатить — 1.99 USDT` (url=`bot_invoice_url` из CryptoBot)
     - `◀️ Назад` (callback="main_menu")

2. **Никакого `pre_checkout_query` / `successful_payment`** — оплату ловит scheduler.

#### Сообщение после оплаты (отправляется из джобы scheduler)
**Одно сообщение** вместо трёх:

```
✅ Оплата получена!
Подписка активна до 25.06.2026 03:24 UTC

🔑 Твой WireGuard-ключ (.conf файл прикреплён ниже)
📸 QR-код для импорта — следующим сообщением

📖 Как подключиться:
1. Скачай WireGuard:
   • iOS: App Store
   • Android: Google Play
   • Windows/Mac: wireguard.com/install
2. В приложении нажми "+" → "Импорт из файла" или "Сканировать QR"
3. Включи туннель — готово 🎉

Проблемы? @support_username
```

И сразу следом — `answer_document(config_text)` + `answer_photo(qr_bytes)`. То есть **три сообщения сворачиваем в концептуально одно: статус-сообщение + .conf + QR подряд, без разрывов**.

#### `bot/handlers/key.py`
Существующий хендлер `get_key` — оставить, но переделать чтобы тоже отдавал **в новом формате** (одним блоком с инструкцией).

#### `bot/handlers/instructions.py` и `support.py`
Тексты обновить под бренд UnLock. Без изменений в логике.

#### `bot/handlers/subscription.py`
Можно удалить (его функция теперь в `/start` welcome для активных). Если оставлять — переделать в дублирующий show-status.

---

## Чек-лист удаления

Удалить / выпилить:
- [ ] `services/payment.py` → удалить (или оставить только если нужны константы `PLANS`)
- [ ] Использование `PAYMENT_TOKEN` в коде
- [ ] `bot/keyboards/tariffs.py` → удалить (тарифы теперь в landing_keyboard)
- [ ] `pre_checkout_query` хендлер
- [ ] `successful_payment` хендлер
- [ ] FSM-states `BuyStates` (они больше не нужны — флоу синхронный)

Оставить как есть:
- [ ] `services/wireguard.py`, `services/subscription.py`, `services/qrcode.py`
- [ ] `database/models.py` структура User/Subscription/WireguardKey (только `Payment` модифицируем)
- [ ] `bot/handlers/admin.py` (`/test_key`)
- [ ] `bot/handlers/instructions.py`, `support.py` (только тексты)
- [ ] `scheduler/tasks.py` — джобы для напоминаний / экспирации (добавить только новую `poll_cryptobot_payments`)

---

## Тесты (минимальный набор)

1. **CryptoBot client unit tests** (с моком aiohttp):
   - `create_invoice` → корректный POST
   - `get_invoices_by_status` → корректный GET + парсинг
   - Обработка ошибок API

2. **Polling job integration test:**
   - Эмулируем paid invoice → проверяем что подписка создалась, ключ выдался, повторный запуск не дублирует

3. **UX smoke:**
   - `/start` без подписки → landing
   - `/start` с подпиской → active status
   - `buy:1m` → инвойс создан в БД

---

## .env additions

```
CRYPTOBOT_TOKEN=<получить в @CryptoBot → Crypto Pay → Create App>
```

Удалить `PAYMENT_TOKEN` (или оставить пустым для совместимости).

---

## Файл баннера

Уже скачан в `/Users/egoordd/vpn-bot/assets/banner.png` (1.3 MB, 1376×768). Использовать в `start.py` через `FSInputFile("assets/banner.png")`.

При деплое — закоммитить и запушить, либо забить путь относительно WORKDIR в Dockerfile.

---

## Порядок работы для Codex

1. **Бэкап БД** на VPS перед миграцией: `docker compose exec postgres pg_dump -U vpn_bot vpn_bot > backup.sql`
2. Модель `Payment` → новые поля (нужен ручной `ALTER TABLE` на проде)
3. `services/cryptobot.py` — клиент
4. `repository.py` — методы для CryptoBot-платежей
5. `scheduler/tasks.py` — джоба `poll_cryptobot_payments`
6. UX-редизайн (`start.py`, `buy.py`, `keyboards/main_menu.py`)
7. Удаление Stars-кода
8. Локальная проверка
9. Деплой: git push → на сервере git pull + alter table + docker compose up -d --build bot

---

## Acceptance criteria

- [ ] `/start` без подписки показывает баннер + 3 тарифа в рублях + кнопку поддержки
- [ ] `/start` с активной подпиской показывает дату окончания + "Получить ключ"
- [ ] Клик "30 дней — 149₽" создаёт CryptoBot-инвойс на 1.99 USDT, шлёт кнопку "Оплатить"
- [ ] После оплаты в CryptoBot — в течение 30 секунд приходит сообщение с конфигом + QR + инструкцией
- [ ] Повторная оплата того же инвойса не создаёт второй ключ
- [ ] Stars-флоу полностью удалён, `pre_checkout_query` не висит в коде
- [ ] `/test_key` для админов продолжает работать
- [ ] Бот не падает при остановленном CryptoBot API (graceful degradation)

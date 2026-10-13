# «Avangard GT» — отдельный Marzban заказчика + бот (13.10.2026)

Третий заказчик (после Etalon и Plata) — тот, кому 13.10 выдана тест-ссылка `exp_denl_7d`.
Решение владельца: **полностью отдельный Marzban на новом сервере** (к нашей панели доступа нет),
серверы **как в тест-ссылке** — 🇩🇪 Германия + 🇳🇱 Нидерланды и ⚡️ Авто-обход без российских серверов,
бот **как Etalon** (тест-драйв 3 дня / 2 устройства / 10 ГБ, тарифы на витрине, оплата — заглушка,
поддержка-тикеты админу), тема `avangard` (графит + racing red, баннеры
`scripts/make_avangard_banners.py`, аватар `marat_bot/themes/assets/avangard/avatar.png`,
картинка описания `description.jpg` — ставит владелец/заказчик в BotFather).

## Состав

| Что | Где |
|---|---|
| Панель Marzban (docker) + выход 🇳🇱 | VPS №1 в Нидерландах (2 vCPU, ≥2 ГБ, Ubuntu 24.04) |
| Выход 🇩🇪 (marzban-node) | VPS №2 в Германии (1 vCPU, ≥1 ГБ) — подключается к панели №1 |
| Бот @avangardgt_bot | VPS №1, служба `avangard-vpnbot`, ходит в панель по `http://127.0.0.1:8000` |
| Вход из России | мост на российском адресе (как в тест-ссылке через VK) — иначе домашние провайдеры режут скорость до 4–6 Мбит/с |

## Окружение бота `/etc/avangard-bot.env` (root:avangard 640)

```
MARAT_BOT_TOKEN=…            # ключ бота — только здесь, в репозиторий не класть
MARAT_NAME="Avangard GT"
MARAT_PREFIX=corp_avg_
MARAT_THEME=avangard
MARAT_PANEL_URL=http://127.0.0.1:8000
MARAT_PANEL_USERNAME=…       # отдельный админ панели для бота (не sudo заказчика)
MARAT_PANEL_PASSWORD=…
MARAT_INBOUNDS=<теги входов NL и DE в его панели через запятую>
MARAT_SUB_BASE=https://<адрес подписок>
MARAT_ADMINS=<ник заказчика>
```

## Код бота на сервере

Нужны только `marat_bot/` и `services/__init__.py` + `services/marzban_client.py`
(клиент панели работает без настроек основного бота, если передан адрес и логин),
зависимость — `aiohttp`. Каталог `/opt/avangard-bot`, venv `/opt/avangard-bot/.venv`,
пользователь `avangard`, юнит — `avangard-vpnbot.service` из этой папки.

## Чего нет в «голом» Marzban (делается отдельно)

- **Лимит устройств** у нас считает шлюз подписок — в чистом Marzban его нет.
- **Авто-обход** (leastPing-балансировщик в JSON для Happ) — тоже от шлюза; для его панели
  нужен свой экземпляр шлюза или заголовки Happ на nginx перед подпиской.

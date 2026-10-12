# Бот «Марат VPN» (@marattesvpn_bot)

Отдельный бот с бесплатным пробным доступом: без оплаты, без картинок, без упоминаний
основного проекта. Код — `marat_bot/`, служба `marat-vpnbot` на бот-сервере
(WorkingDirectory=/opt/vpn-bot, тот же .venv и доступ к панели, что у основного бота).
Ключ бота — `/etc/marat-bot.env` (`MARAT_BOT_TOKEN=…`, root:unlockapp 640).
Кто брал пробник — `/var/lib/marat-bot/users.sqlite3` (один на аккаунт Telegram).

Пробник: учётка панели `corp_mrt_<telegram id>`, входы VLESS Reality PL / FI2 / AMS / US2,
3 дня, 10 ГБ. Остальное делает шлюз по шаблону `corp_mrt_*` в `/etc/unlock-subgw.env`:
`SUB_TITLES` (название «Марат VPN»), `UNBRANDED_USERS` (без объявлений, поддержки и сайта),
`COMPACT_USERS` (по пункту на страну + Авто-обход + РУ-режим), `MANUAL_DEVICE_LIMITS` (2),
`USER_SHARED_CORP_HOSTS` (Финляндия-2), `SUB_BASES` (адрес `https://m.212.233.122.241.sslip.io`
на VK-фронте, nginx `/etc/nginx/sites-available/marat-front`).

Выкладка кода: скопировать `marat_bot/` в `/opt/vpn-bot/marat_bot/` (без macOS-файлов `._*`),
`systemctl restart marat-vpnbot`.

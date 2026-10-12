# Бот «Ярослав VPN» (@yaroslavtestvpn_bot)

Второй заказчик на том же коде, что «Марат VPN» (`marat_bot/`), со своей темой оформления
`orbit` (`marat_bot/themes/orbit.py`). Служба `yaroslav-vpnbot` на бот-сервере, окружение
`/etc/yaroslav-bot.env` (root:unlockapp 640):

```
MARAT_BOT_TOKEN=…
MARAT_NAME="Ярослав VPN"
MARAT_PREFIX=corp_yar_
MARAT_THEME=orbit
MARAT_SUB_BASE=https://y.212.233.122.241.sslip.io
MARAT_ADMINS=
```

База — `/var/lib/yaroslav-bot/users.sqlite3`. Учётки панели `corp_yar_<telegram id>`, те же входы
и сроки, что у Марата (3 дня, 10 ГБ, 2 устройства). В `/etc/unlock-subgw.env` шаблон `corp_yar_*`
добавлен туда же, где `corp_mrt_*`: `SUB_TITLES`, `UNBRANDED_USERS`, `COMPACT_USERS`,
`MANUAL_DEVICE_LIMITS`, `USER_SHARED_CORP_HOSTS`, `SUB_BASES`. Адрес подписки — nginx
`/etc/nginx/sites-available/yaroslav-front` на VK-фронте (копия `marat-front`).

Выкладка кода — как у Марата, затем `systemctl restart marat-vpnbot yaroslav-vpnbot`.

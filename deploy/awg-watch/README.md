# Сторож AmneziaWG-клиентов на роутерах

`scripts/awg_peer_watch.py` раз в 5 минут (таймер `unlock-awg-watch.timer` на бот-сервере
23.95.3.18) берёт у польского сервера время последних рукопожатий входа `awg1` и пишет
в бот уведомлений (`services.alerts.send_alert`), только когда роутер клиента пропал
дольше 15 минут или вернулся. Первый запуск молчит. Состояние —
`/var/lib/unlock-awg-watch/state.json`.

Доступ к польскому серверу — отдельный ключ `/root/.ssh/awg_watch`, в
`/root/.ssh/authorized_keys` на PL он ограничен:
`from="23.95.3.18",command="/usr/bin/awg show awg1 latest-handshakes",restrict`.

Добавить роутер: дописать в `AWG_WATCH` юнита «публичный ключ клиента|подпись» через `;`,
затем `systemctl daemon-reload`. Ключ клиента — в `/etc/amnezia/amneziawg/awg1.conf` на PL
под строкой `# <имя>`.

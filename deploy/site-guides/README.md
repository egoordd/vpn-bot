# Инструкции на сайте (статикой, мимо Next.js)

Страницы отдаёт nginx на сервере сайта (168.113.210.6) из `/var/www/guides/<имя>/`,
сам сайт (Next.js на :3000) не пересобирается. Запросы приходят через VK-фронт
212.233.122.241, он проксирует всё, кроме `/sub|happ|incy`, на сервер сайта.

| Адрес | Файлы |
|---|---|
| https://unlockproject.site/keenetic/ | `keenetic/index.html` → `/var/www/guides/keenetic/index.html` |

## Выкладка

```bash
scp keenetic/index.html root@168.113.210.6:/tmp/keenetic-guide.html
ssh root@168.113.210.6 'install -m 644 /tmp/keenetic-guide.html /var/www/guides/keenetic/index.html'
```

SSH к серверу сайта — только через VK-прыжок (см. память project_site_ru_vps).

## nginx (`/etc/nginx/sites-enabled/unlockproject`, блок `listen 443`)

```nginx
location = /keenetic {
    return 301 https://unlockproject.site/keenetic/;
}
location /keenetic/ {
    alias /var/www/guides/keenetic/;
    index index.html;
    add_header X-Robots-Tag "noindex, nofollow" always;
    add_header Cache-Control "no-cache" always;
}
```

## Что не класть на публичную страницу

- IP серверов и параметры маскировки AmneziaWG (Jc…H4): по ним протокол легко опознать и заблокировать.
  Команда для командной строки роутера собирается в браузере клиента из его собственного файла.
- Файлы `.conf` и ключи: у каждого клиента свой личный файл.
- Сейчас (11.10.2026) на шагах 2–6 скриншоты с wiki.rockblack.tech с подписью-источником — решение владельца под сдачу работы; заменить своими при первой возможности (файлы `keenetic/img/*.webp`, имена те же).

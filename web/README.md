# UnLock — web (сайт + кабинет)

Next.js (App Router) витрина и личный кабинет для VPN-подписки UnLock.
Фаза 3, пункт 33 плана. Сайт сидит поверх общего биллинг-слоя
(`../services/billing_api.py`) через серверный клиент-шов
(`src/lib/billing/client.ts`).

## Запуск

```bash
cd web
npm install
cp .env.example .env.local
npm run dev
```

Открыть http://localhost:3000 — лендинг, http://localhost:3000/cabinet — кабинет.

Без `BILLING_API_URL` сайт работает на детерминированных мок-данных
(`src/lib/billing/mock.ts`), чтобы UI крутился автономно при дизайне/превью.

## Скрипты

| Команда | Что делает |
|---|---|
| `npm run dev` | dev-сервер |
| `npm run build` | прод-сборка |
| `npm run start` | прод-сервер |
| `npm run typecheck` | `tsc --noEmit` |

## Конфигурация (`.env.local`)

| Переменная | Назначение |
|---|---|
| `NEXT_PUBLIC_SITE_URL` | канонический origin (метаданные) |
| `NEXT_PUBLIC_TELEGRAM_BOT` | username бота (без `@`) — диплинки и Login Widget |
| `BILLING_API_URL` | HTTP-эндпоинт Python биллинг-API; пусто → моки |
| `BILLING_API_TOKEN` | bearer-токен к биллинг-API |

## Структура

```
src/
├── app/                     # маршруты (App Router)
│   ├── page.tsx             # лендинг
│   ├── cabinet/page.tsx     # личный кабинет
│   └── api/                 # route handlers: plans, account, promo
├── components/              # по фиче: hero, features, how, pricing, faq,
│   │                        #          cta, trust, nav, cabinet, ui
├── lib/
│   ├── billing/             # шов к Python billing_api (types/mock/client)
│   ├── tariffs.ts           # зеркало services/tariffs.py
│   ├── money.ts             # зеркало services/money.py (копейки RUB)
│   └── ...
└── styles/                  # tokens.css, typography.css
```

## Что готово / что дальше

- ✅ Лендинг: hero (анимированный «туннель»), trust-bar, features (bento),
  how-it-works, pricing (переключатель Standard/Premium), FAQ, CTA, footer.
- ✅ Кабинет: подписка (трафик/срок), кошелёк (баланс + история), рефералка,
  промокод (форма → `/api/promo`), подключение устройств.
- ✅ Серверный шов к биллингу + моки; security-заголовки в `next.config.mjs`.
- ⬜ **Аутентификация** — Telegram Login Widget / email (сейчас demo `userId=1`).
- ⬜ **HTTP-обёртка над `billing_api.py`** (FastAPI) и подключение `BILLING_API_URL`.
- ⬜ **Оплата**: карточный PSP (РФ) + крипта, реальные checkout-флоу.
- ⬜ ESLint-конфиг (билд сейчас не гоняет eslint, типобезопасность — через `tsc`).

> Дизайн-направление: тёмный «secure/stealth», один сигнальный акцент
> (mint-green = соединение живо), violet — premium. Токены — `src/styles/tokens.css`.

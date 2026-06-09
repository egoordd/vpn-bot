# Billing API — общий слой (бот + сайт)

> `services/billing_api.py` — единая точка входа в биллинг для Telegram-бота и
> будущего сайта (Next.js). Транспорт сайта (HTTP-ручки) кладётся **поверх** этих
> функций, а не поверх нижележащих сервисов. Пункт 32 плана.

## Денежная единица

Всё внутреннее (баланс, ledger, скидки, начисления) считается в **копейках рубля**
(целые числа). Цены тарифов заданы в целых рублях (`Tariff.price_rub`), поэтому
`1 RUB == 100 копеек`. Конвертация и форматирование — `services/money.py`
(`rubles_to_kopecks`, `kopecks_to_rubles`, `format_rub`, `percent_of`).

> CryptoBot выставляет счёт в USDT (`crypto_amount`). Конвертация пополнения
> USDT→баланс (FX-курс) пока НЕ реализована: `wallet.deposit` принимает уже
> посчитанные копейки. Это сознательный TODO для интеграции пополнения.

## Каталог и оплата (существующее)

- `list_billing_plans` / `get_billing_plan` / `list_billing_regions` — каталог тарифов и premium-локаций (DTO).
- `build_payment_intent` — собирает `PaymentIntent` (резолв тарифа, валидация premium-региона, `get_or_create_user`, payload, сумма в minor-units).
- `register_cryptobot_payment` — записывает pending CryptoBot-платёж.
- `get_subscription_snapshot` / `activate_access` — состояние и активация подписки через панель.

## Аккаунт, кошелёк, рефералка, промокоды (Фаза 3)

| Функция | Назначение |
|---|---|
| `get_account_overview(session, user_id)` | Композитный `AccountOverview`: подписка + кошелёк + рефералка + `balance_display`. Это данные кабинета (бот и сайт). |
| `get_wallet(session, user_id)` | `WalletSnapshot`: баланс (копейки) + последние операции. |
| `redeem_balance_promo(session, *, user_id, code)` | Активировать промокод-бонус на баланс. |
| `preview_checkout_discount(session, *, user_id, code, amount_kopecks)` | Посчитать скидку промокода на чек (не списывает использование). |
| `get_referral_overview(session, user_id)` | `ReferralStats`: код, % награды, число рефералов, заработано. |
| `attach_referral_code(session, *, user_id, ref_code)` | Привязать реферера (один раз, не сам на себя). |
| `reward_referral_for_payment(session, *, paid_user_id, plan_code, payment_reference)` | Начислить рефереру % при оплате. Идемпотентно по `payment_reference`. |

## Кошелёк (`services/wallet.py`)

- Ledger `WalletTransaction` — **append-only**: каждый кредит/дебет добавляет строку с
  знаковым `amount` и итоговым `balance_after`. Кэш-сумма — `users.balance`.
- `deposit` / `spend` — атомарны: `UPDATE users SET balance=balance±X WHERE id=? [AND balance>=X] RETURNING balance`.
- `spend` бросает `InsufficientBalanceError`; операции по несуществующему юзеру — `UnknownWalletUserError`.
- Виды операций (`kind`): `deposit`, `spend`, `referral_reward`, `promo_bonus`, `refund`, `adjustment`.

## Рефералка (`services/referral.py`)

- Код реферера — `users.ref_code` (по умолчанию `tg<telegram_id>`). Диплинк: `https://t.me/<bot>?start=ref_<code>`.
- `parse_referral_start_payload("ref_<code>")` → `<code>` — парсинг `/start`-пейлоада.
- Награда — `REFERRAL_REWARD_PERCENT = 20`% от `price_rub` тарифа, на баланс реферера.
- Начисление подключено в `scheduler.poll_cryptobot_payments` (best-effort: ошибка награды не ломает выдачу доступа).

## Промокоды (`services/promo.py`)

Тип (`PromoCode.kind`) задаёт смысл `value`:

| kind | `value` | применение |
|---|---|---|
| `balance_bonus` | копейки | `redeem_balance_promo` → зачисление на баланс |
| `percent_discount` | проценты | `preview_discount` / `apply_discount` на чек |
| `fixed_discount` | копейки | `preview_discount` / `apply_discount` (скидка не больше суммы чека) |

Лимиты: `max_uses` (общий), `per_user_limit` (на юзера, через `promo_redemptions`),
`expires_at`, `min_amount_kopecks`. Списание использования атомарно
(`claim_promo_use`: `UPDATE … WHERE used_count<max_uses RETURNING`).

## Следующие шаги (нужно участие/секреты)

1. HTTP-транспорт (FastAPI/ASGI) поверх этих функций — контракт для сайта (33).
2. Промокод/скидка и оплата балансом в самом buy-флоу бота + UX кабинета.
3. Пополнение баланса (USDT→RUB FX) и карточный PSP (34).

"use client";

import { useEffect, useMemo, useState } from "react";

import { PAY_METHODS, SITE } from "@/lib/site";
import { PLANS, pricePerMonth, savingPercent, type Tariff } from "@/lib/tariffs";
import "./checkout.css";

const LABELS: Record<string, string> = { "1m": "1 месяц", "3m": "3 месяца", "6m": "6 месяцев", "12m": "12 месяцев" };
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function rub(value: number): string {
  return `${value.toLocaleString("ru-RU")} ₽`;
}

/**
 * Оформление подписки Plata на сайте: тариф → e-mail → согласие → оплата на странице платёжного
 * сервиса (ЮKassa). Пока ключи магазина не подключены — после проверки формы показываем заглушку.
 */
export function Checkout() {
  const [code, setCode] = useState("12m");
  const [email, setEmail] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [touched, setTouched] = useState(false);
  const [stub, setStub] = useState(false);

  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("plan");
    if (wanted && PLANS.some((p) => p.code === wanted)) setCode(wanted);
  }, []);

  const plan: Tariff = useMemo(() => PLANS.find((p) => p.code === code) ?? PLANS[PLANS.length - 1], [code]);
  const emailOk = EMAIL_RE.test(email.trim());
  const ready = emailOk && agreed;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (ready) setStub(true);
  }

  return (
    <div className="co">
      <section className="co__plans" aria-label="Срок подписки">
        {PLANS.map((p) => {
          const saving = savingPercent(p);
          return (
            <button
              key={p.code}
              type="button"
              className={`co__plan${p.code === code ? " is-active" : ""}`}
              aria-pressed={p.code === code}
              onClick={() => {
                setCode(p.code);
                setStub(false);
              }}
            >
              <span className="co__plan-term">{LABELS[p.code]}</span>
              <span className="co__plan-price">{rub(p.priceRub)}</span>
              <span className="co__plan-per">
                {rub(pricePerMonth(p))} в месяц{saving > 0 ? ` · −${saving}%` : ""}
              </span>
            </button>
          );
        })}
      </section>

      <form className="co__form" onSubmit={submit} noValidate>
        <div className="co__summary">
          <div>
            <span className="eyebrow">Ваш заказ</span>
            <h2>{SITE.name} — {LABELS[plan.code]}</h2>
            <p className="muted">4 страны, авто-выбор сервера и до {plan.deviceLimit} устройств</p>
          </div>
          <strong className="co__total">{rub(plan.priceRub)}</strong>
        </div>

        <label className="co__field">
          <span>Электронная почта</span>
          <input
            type="email"
            inputMode="email"
            autoComplete="email"
            placeholder="name@example.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setStub(false);
            }}
            onBlur={() => setTouched(true)}
            aria-invalid={touched && !emailOk}
            required
          />
          <small className={touched && !emailOk ? "is-error" : ""}>
            {touched && !emailOk
              ? "Введите адрес почты, например name@example.com"
              : "На неё придут чек и доступ к подписке"}
          </small>
        </label>

        <fieldset className="co__methods">
          <legend>Способ оплаты</legend>
          <label className="co__method is-soon">
            <input type="radio" name="method" checked readOnly disabled />
            <span>
              <b>Карта, СБП или SberPay</b>
              <em>На защищённой странице платёжного сервиса — данные карты мы не видим</em>
            </span>
            <i className="co__badge">Скоро</i>
          </label>
        </fieldset>

        <label className="co__agree">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>
            Соглашаюсь с <a href="/terms/">пользовательским соглашением</a> и{" "}
            <a href="/privacy/">политикой конфиденциальности</a>
          </span>
        </label>
        {touched && !agreed && <p className="co__hint is-error">Нужно согласие с условиями</p>}

        <button type="submit" className="btn btn--navy btn--lg co__pay">
          Перейти к оплате · {rub(plan.priceRub)}
        </button>

        {stub && (
          <div className="co__stub" role="status">
            <b>Оплата на сайте скоро будет доступна</b>
            <p>
              Мы подключаем приём платежей ({PAY_METHODS}). Как только он заработает, оформить подписку можно
              будет здесь же — на почту {email.trim()} придут чек и доступ. А пока попробуйте Plata бесплатно в{" "}
              <a href={`https://t.me/${SITE.botUsername}?start=site`} target="_blank" rel="noopener noreferrer">
                боте @{SITE.botUsername}
              </a>
              .
            </p>
          </div>
        )}

        <p className="co__note">
          Оплата разовая, без автосписаний. Условия возврата — в разделе 7{" "}
          <a href="/terms/#refund">пользовательского соглашения</a>.
        </p>
      </form>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";

import { PLANS, pricePerMonth, savingPercent, type Tariff } from "@/lib/tariffs";
import "./checkout.css";

const LABELS: Record<string, string> = { "1m": "1 месяц", "3m": "3 месяца", "6m": "6 месяцев", "12m": "12 месяцев" };
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function rub(value: number): string {
  return `${value.toLocaleString("ru-RU")} ₽`;
}

/**
 * Оформление подписки на сайте (14.10.2026, требование Platega): тариф → e-mail → согласие →
 * способ оплаты. Оплата по СБП ещё не подключена — после проверки формы показываем заглушку,
 * в бот с сайта при оплате не уводим.
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
            <span className="overline">Ваш заказ</span>
            <h2>Etalon VPN — {LABELS[plan.code]}</h2>
            <p className="muted">Все серверы, Авто-выбор и до {plan.deviceLimit} устройств</p>
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
              <b>СБП</b>
              <em>QR-код или оплата по ссылке из приложения банка</em>
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

        <button type="submit" className="btn btn--gold co__pay">
          Перейти к оплате · {rub(plan.priceRub)}
        </button>

        {stub && (
          <div className="co__stub" role="status">
            <b>Оплата по СБП скоро будет доступна</b>
            <p>
              Мы подключаем приём платежей. Как только оплата по СБП заработает, оформить подписку можно будет
              здесь же — на почту {email.trim()} придут чек и доступ.
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

import { PAY_METHODS } from "@/lib/site";
import { PLANS, pluralDays, pricePerMonth, savingPercent } from "@/lib/tariffs";
import { Chevron } from "../ui/ui";
import "./pricing.css";

export const TERM_LABELS: Record<string, string> = { "1m": "1 месяц", "3m": "3 месяца", "6m": "6 месяцев", "12m": "12 месяцев" };
const INCLUDED = ["4 страны и авто-выбор сервера", "Банки и Госуслуги без отключения", "До 5 устройств"] as const;
const FEATURED = "12m";

function rub(value: number): string {
  return `${value.toLocaleString("ru-RU")} ₽`;
}

export function Pricing() {
  return (
    <section className="section pricing" id="pricing" aria-labelledby="pricing-title">
      <div className="wrap">
        <div className="section-head">
          <span className="eyebrow">Тарифы</span>
          <h2 id="pricing-title">Один набор возможностей — выберите только срок</h2>
          <p>Во всех тарифах одно и то же. Чем дольше срок, тем ниже цена за месяц.</p>
        </div>
        <ul className="plans">
          {PLANS.map((plan) => {
            const saving = savingPercent(plan);
            const featured = plan.code === FEATURED;
            return (
              <li key={plan.code} className={`plan${featured ? " plan--featured" : ""}`}>
                {featured && <span className="plan__ribbon">Выгоднее всего</span>}
                <div className="plan__top">
                  <h3>{TERM_LABELS[plan.code]}</h3>
                  {saving > 0 && <span className="plan__save">−{saving}%</span>}
                </div>
                <p className="plan__price">{rub(plan.priceRub)}</p>
                <p className="plan__per">
                  {rub(pricePerMonth(plan))} в месяц · {pluralDays(plan.durationDays)}
                </p>
                <ul className="plan__list">
                  {INCLUDED.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <a className="plan__cta" href={`/checkout/?plan=${plan.code}`}>
                  Выбрать <Chevron />
                </a>
              </li>
            );
          })}
        </ul>
        <p className="pricing__note">
          Оплата разовая, без автосписаний — {PAY_METHODS} на защищённой странице платёжного сервиса. Подробно — в
          разделе <a href="/tariffs/">«Тарифы и оплата»</a>.
        </p>
      </div>
    </section>
  );
}

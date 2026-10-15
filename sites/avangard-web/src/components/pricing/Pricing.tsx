import { botLink } from "@/lib/site";
import { PLANS, TRIAL, TRIAL_DAYS_LABEL, pluralDays, pricePerMonth, savingPercent } from "@/lib/tariffs";
import { Button } from "../ui/ui";
import "./pricing.css";

const TERMS: Record<string, string> = { "1m": "1 месяц", "3m": "3 месяца", "6m": "6 месяцев", "12m": "12 месяцев" };
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
          <h2 id="pricing-title">Ключ на выбранный срок</h2>
          <p>Во всех тарифах одно и то же: обе страны, авто-выбор и до 5 устройств. Чем дольше срок — тем ниже цена за месяц.</p>
        </div>
        <ul className="keys">
          {PLANS.map((plan) => {
            const saving = savingPercent(plan);
            const featured = plan.code === FEATURED;
            return (
              <li key={plan.code} className={`key${featured ? " key--featured" : ""}`}>
                {featured && <span className="key__ribbon">Лучшая цена</span>}
                <h3>{TERMS[plan.code]}</h3>
                <p className="key__price">{rub(plan.priceRub)}</p>
                <p className="key__per">
                  {rub(pricePerMonth(plan))} в месяц · {pluralDays(plan.durationDays)}
                </p>
                {saving > 0 ? <span className="key__save">выгода {saving}%</span> : <span className="key__save key__save--none">помесячно</span>}
              </li>
            );
          })}
        </ul>
        <div className="pricing__foot">
          <Button href={botLink("site")} size="lg" external>
            Начать с {TRIAL_DAYS_LABEL} бесплатно
          </Button>
          <p>
            Пробный период — до {TRIAL.deviceLimit} устройств, без карты. Оплата разовая, без автосписаний; приём
            оплаты подключается — подробности в разделе <a href="/tariffs/">«Тарифы и оплата»</a>.
          </p>
        </div>
      </div>
    </section>
  );
}

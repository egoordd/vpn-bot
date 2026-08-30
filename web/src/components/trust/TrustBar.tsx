import "./trust.css";
import { LIVE_COUNTRIES_LABEL } from "@/lib/locations";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";

const ITEMS = [
  { value: "1 тап", label: "подключение без настроек" },
  { value: TRIAL_DAYS_LABEL, label: "бесплатно, без оплаты" },
  { value: LIVE_COUNTRIES_LABEL, label: "и новые на подходе" },
  { value: "24/7", label: "стабильная скорость" },
];

export function TrustBar() {
  return (
    <section className="trust" aria-label="Ключевые факты">
      <div className="container">
        <ul className="trust__row">
          {ITEMS.map((item) => (
            <li key={item.label} className="trust__item">
              <span className="trust__value">{item.value}</span>
              <span className="trust__label">{item.label}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

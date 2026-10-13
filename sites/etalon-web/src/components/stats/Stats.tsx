import { TRIAL } from "@/lib/tariffs";
import "./stats.css";

const ITEMS = [
  { value: "4", label: "страны", note: "Польша, Финляндия, Нидерланды, США" },
  { value: "5", label: "устройств", note: "в любом тарифе, на одной подписке" },
  { value: String(TRIAL.durationDays), label: "дня бесплатно", note: "без оплаты и привязки карты" },
];

export function Stats() {
  return (
    <section className="stats" aria-label="Коротко об Etalon">
      <div className="container stats__row">
        {ITEMS.map((item) => (
          <div key={item.label} className="stats__item reveal">
            <span className="stats__value">{item.value}</span>
            <div>
              <span className="stats__label">{item.label}</span>
              <span className="stats__note">{item.note}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

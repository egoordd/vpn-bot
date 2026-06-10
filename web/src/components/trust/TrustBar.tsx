import "./trust.css";

const ITEMS = [
  { value: "LTE", label: "проверено на реальном операторе" },
  { value: "Reality", label: "маскировка под HTTPS" },
  { value: "7 дней", label: "бесплатный пробник" },
  { value: "24/7", label: "автоскейл нод под нагрузку" },
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

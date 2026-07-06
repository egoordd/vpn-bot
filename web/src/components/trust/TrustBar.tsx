import "./trust.css";

const ITEMS = [
  { value: "1 тап", label: "подключение без настроек" },
  { value: "3 дня", label: "бесплатно, без оплаты" },
  { value: "2 страны", label: "и новые на подходе" },
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

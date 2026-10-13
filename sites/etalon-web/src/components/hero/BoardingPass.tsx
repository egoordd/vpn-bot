import { LogoMark } from "@/components/ui/LogoMark";

const FIELDS = [
  { label: "Пассажир", value: "Вы" },
  { label: "Рейс", value: "ETL 001" },
  { label: "Класс", value: "Эталон" },
  { label: "Выход", value: "⚡️ Авто" },
  { label: "В пути", value: "≈ 35 мс" },
  { label: "Багаж", value: "до 5 устр." },
];

/** Посадочный талон: откуда — Россия, куда — весь интернет. Корешок с штрихкодом отделён перфорацией. */
export function BoardingPass() {
  return (
    <figure className="pass" aria-label="Посадочный талон Etalon VPN: из России во весь интернет">
      <div className="pass__main">
        <header className="pass__top">
          <span className="pass__brand">
            <LogoMark className="pass__key" /> ETALON VPN
          </span>
          <span className="pass__tag">Boarding pass</span>
        </header>

        <div className="pass__route">
          <div>
            <span className="pass__code">RUS</span>
            <span className="pass__city">Россия</span>
          </div>
          <svg className="pass__plane" viewBox="0 0 64 24" aria-hidden>
            <path d="M2 12h44" strokeDasharray="3 5" />
            <path d="M48 4l12 8-12 8 3-8z" />
          </svg>
          <div className="pass__to">
            <span className="pass__code">WWW</span>
            <span className="pass__city">Весь интернет</span>
          </div>
        </div>

        <dl className="pass__fields">
          {FIELDS.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="pass__stub" aria-hidden>
        <span className="pass__stub-label">Посадка</span>
        <span className="pass__stub-value">Сейчас</span>
        <span className="pass__barcode" />
      </div>
    </figure>
  );
}

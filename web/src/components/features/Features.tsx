import { Pill } from "@/components/ui/Pill";
import "./features.css";

interface Feature {
  title: string;
  body: string;
  span: "wide" | "tall" | "normal";
  glyph: React.ReactNode;
  tag?: string;
}

const FEATURES: Feature[] = [
  {
    title: "Маскировка под обычный сайт",
    body:
      "Reality прячет трафик под настоящий HTTPS-хэндшейк с валидным сертификатом. Для оператора это неотличимо от захода на сайт — нечего блокировать.",
    span: "wide",
    tag: "Анти-DPI",
    glyph: <GlyphShield />,
  },
  {
    title: "Ссылка-подписка",
    body: "Один раз импортируете ссылку в приложение — дальше конфиг обновляется сам.",
    span: "normal",
    glyph: <GlyphLink />,
  },
  {
    title: "Серверы под нагрузку",
    body: "Автоскейлер поднимает ноды по спросу и гасит пустые. Меньше соседей — стабильнее скорость.",
    span: "tall",
    tag: "Автоскейл",
    glyph: <GlyphServer />,
  },
  {
    title: "Несколько устройств",
    body: "Телефон, ноутбук, планшет — по одной подписке, лимит зависит от тарифа.",
    span: "normal",
    glyph: <GlyphDevices />,
  },
  {
    title: "Оплата как удобно",
    body: "Карта РФ, криптовалюта, баланс кошелька. Платёж можно провести и вне Telegram — на сайте.",
    span: "wide",
    glyph: <GlyphCard />,
  },
];

export function Features() {
  return (
    <section id="features" className="section features" aria-labelledby="features-heading">
      <div className="container">
        <header className="features__head">
          <span className="eyebrow">Почему UnLock</span>
          <h2 id="features-heading">Сделан, чтобы пережить блокировки</h2>
          <p className="lead features__sub">
            Не «ещё один VPN», а связка протокола и инфраструктуры, заточенная под
            враждебные сети российских операторов.
          </p>
        </header>

        <div className="features__grid">
          {FEATURES.map((f) => (
            <article key={f.title} className={`feature feature--${f.span}`}>
              <div className="feature__glyph" aria-hidden>
                {f.glyph}
              </div>
              <div className="feature__text">
                {f.tag && <Pill tone="accent">{f.tag}</Pill>}
                <h3 className="feature__title">{f.title}</h3>
                <p className="feature__body">{f.body}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function GlyphShield() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" fill="none">
      <path d="M16 3 5 7v8c0 7 4.7 11.5 11 14 6.3-2.5 11-7 11-14V7L16 3Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="m11 16 3.5 3.5L22 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function GlyphLink() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" fill="none">
      <path d="M13 19a4.5 4.5 0 0 0 6.4 0l3.6-3.6a4.5 4.5 0 1 0-6.4-6.4L14.5 10.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M19 13a4.5 4.5 0 0 0-6.4 0L9 16.6a4.5 4.5 0 1 0 6.4 6.4l2.1-2.1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function GlyphServer() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" fill="none">
      <rect x="5" y="6" width="22" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <rect x="5" y="18" width="22" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="10" cy="10" r="1.3" fill="currentColor" />
      <circle cx="10" cy="22" r="1.3" fill="currentColor" />
    </svg>
  );
}
function GlyphDevices() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" fill="none">
      <rect x="4" y="7" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <rect x="20" y="13" width="8" height="13" rx="2" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
function GlyphCard() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" fill="none">
      <rect x="4" y="8" width="24" height="16" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4 13h24" stroke="currentColor" strokeWidth="1.8" />
      <path d="M9 19h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

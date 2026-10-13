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
    title: "Авто-выбор сервера",
    body:
      "Первый пункт в приложении сам проверяет серверы и держит соединение на самом быстром. Никаких ручных настроек и перебора стран.",
    span: "wide",
    tag: "Авто",
    glyph: <GlyphServer />,
  },
  {
    title: "Одна ссылка — и всё",
    body: "Добавили ссылку в приложение один раз — дальше всё работает и обновляется само.",
    span: "normal",
    glyph: <GlyphLink />,
  },
  {
    title: "Российские сервисы — без отключения VPN",
    body: "В «Режиме РУ-сервисов» банки, Госуслуги и маркетплейсы открываются напрямую, всё остальное — через VPN.",
    span: "tall",
    tag: "РУ-режим",
    glyph: <GlyphShield />,
  },
  {
    title: "На всех устройствах",
    body: "iPhone, Android, Windows и Mac — до 5 устройств в любом тарифе.",
    span: "normal",
    glyph: <GlyphDevices />,
  },
  {
    title: "Защищённое соединение",
    body: "Трафик идёт по зашифрованному каналу — спокойно в кафе, аэропорту и любом публичном Wi-Fi.",
    span: "wide",
    glyph: <GlyphLock />,
  },
];

export function Features() {
  return (
    <section id="features" className="section features" aria-labelledby="features-heading">
      <div className="container">
        <header className="features__head">
          <span className="eyebrow">Почему Etalon</span>
          <h2 id="features-heading">Всё уже настроено за вас</h2>
          <p className="lead features__sub">
            Никаких сложных настроек. Подключаетесь за минуту и пользуетесь —
            остальное берём на себя.
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
function GlyphLock() {
  return (
    <svg viewBox="0 0 32 32" width="28" height="28" fill="none">
      <rect x="7" y="14" width="18" height="13" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M11 14v-3.5a5 5 0 0 1 10 0V14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="16" cy="20.5" r="1.6" fill="currentColor" />
    </svg>
  );
}

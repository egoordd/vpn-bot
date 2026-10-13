import "./onboard.css";

interface Amenity {
  title: string;
  body: string;
  icon: React.ReactNode;
}

const AMENITIES: Amenity[] = [
  {
    title: "Внутренние рейсы — без пересадок",
    body: "В «Режиме РУ-сервисов» банки, Госуслуги и маркетплейсы открываются напрямую, остальное — через VPN. Выключать ничего не нужно.",
    icon: <IconRoute />,
  },
  {
    title: "Ручная кладь — до 5 устройств",
    body: "Телефон, ноутбук, планшет: одна подписка на всех. iPhone, Android, Windows и Mac.",
    icon: <IconBag />,
  },
  {
    title: "Безопасный полёт",
    body: "Трафик идёт по зашифрованному каналу — спокойно в кафе, аэропорту и любом публичном Wi-Fi.",
    icon: <IconShield />,
  },
  {
    title: "Один посадочный — навсегда",
    body: "Ссылка подписки добавляется в приложение один раз. Новые серверы и настройки приходят сами.",
    icon: <IconTicket />,
  },
];

export function OnBoard() {
  return (
    <section id="onboard" className="section onboard" aria-labelledby="onboard-title">
      <div className="container">
        <header className="section-head reveal">
          <span className="eyebrow">Сервис на борту</span>
          <h2 id="onboard-title">Всё включено в каждый билет</h2>
        </header>

        <div className="onboard__grid">
          <article className="autopilot reveal">
            <div className="autopilot__dial" aria-hidden>
              <svg viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" className="dial__ring" />
                <circle cx="60" cy="60" r="52" className="dial__arc" />
                <path d="M60 60 L60 18" className="dial__needle" />
                <circle cx="60" cy="60" r="5" className="dial__hub" />
              </svg>
              <span className="autopilot__badge">⚡️ АВТО</span>
            </div>
            <div className="autopilot__text">
              <span className="autopilot__tag">Автопилот</span>
              <h3>Лучший маршрут — без вашего участия</h3>
              <p>
                Первый пункт в приложении постоянно сверяет все серверы и держит соединение на самом быстром. Если
                направление начнёт тормозить, автопилот перестроит маршрут сам.
              </p>
            </div>
          </article>

          {AMENITIES.map((a) => (
            <article key={a.title} className="amenity reveal">
              <span className="amenity__icon" aria-hidden>
                {a.icon}
              </span>
              <h3>{a.title}</h3>
              <p>{a.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function IconRoute() {
  return (
    <svg viewBox="0 0 32 32" fill="none">
      <circle cx="8" cy="24" r="3" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="24" cy="8" r="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M10.5 22.5C15 18 13 13 21.5 9.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function IconBag() {
  return (
    <svg viewBox="0 0 32 32" fill="none">
      <rect x="6" y="10" width="20" height="16" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 10V7.5A1.5 1.5 0 0 1 13.5 6h5A1.5 1.5 0 0 1 20 7.5V10" stroke="currentColor" strokeWidth="1.8" />
      <path d="M6 16h20" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
function IconShield() {
  return (
    <svg viewBox="0 0 32 32" fill="none">
      <path d="M16 4 6 8v7c0 6.5 4.3 10.6 10 13 5.7-2.4 10-6.5 10-13V8L16 4Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="m11.5 16 3.2 3.2L21 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconTicket() {
  return (
    <svg viewBox="0 0 32 32" fill="none">
      <path d="M5 10a2 2 0 0 1 2-2h18a2 2 0 0 1 2 2v3a3 3 0 0 0 0 6v3a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-3a3 3 0 0 0 0-6v-3Z" stroke="currentColor" strokeWidth="1.8" />
      <path d="M20 8v16" stroke="currentColor" strokeWidth="1.8" strokeDasharray="2 3" />
    </svg>
  );
}

import "./features.css";

const ITEMS = [
  {
    n: "I",
    title: "Автопилот",
    body: "Первый пункт в приложении сам выбирает самый быстрый сервер и меняет маршрут, если связь начинает проседать. Вы просто включаете VPN.",
  },
  {
    n: "II",
    title: "Российские сервисы — напрямую",
    body: "В режиме РУ-сервисов банки, Госуслуги и маркетплейсы работают как обычно, а остальной трафик идёт через защищённый канал. Выключать VPN не нужно.",
  },
  {
    n: "III",
    title: "Одна подписка — все устройства",
    body: "iPhone, Android, Windows и Mac. До пяти устройств в любом тарифе, одна ссылка обновляется сама.",
  },
  {
    n: "IV",
    title: "Шифрование без компромиссов",
    body: "Трафик идёт по зашифрованному каналу — дома, в кафе, в аэропорту и в любом публичном Wi-Fi.",
  },
];

export function Features() {
  return (
    <section id="features" className="section features" aria-labelledby="features-title">
      <div className="container features__layout">
        <header className="section-head features__head reveal">
          <span className="overline">Преимущества</span>
          <h2 id="features-title">
            Стандарт, <em>по которому</em> сверяют остальных
          </h2>
          <p className="lead">
            Мы убрали всё, что мешает: настройки, выбор серверов, отключения ради банковских приложений.
          </p>
        </header>

        <ol className="features__list">
          {ITEMS.map((item) => (
            <li key={item.n} className="feature reveal">
              <span className="feature__n">{item.n}</span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

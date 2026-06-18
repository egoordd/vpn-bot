import "./faq.css";

const ITEMS = [
  {
    q: "Чем UnLock лучше обычного VPN?",
    a: "Он надёжнее и проще. Соединение остаётся стабильным даже там, где обычные VPN тормозят или постоянно отваливаются, а подключение занимает один тап.",
  },
  {
    q: "Будет ли работать на мобильном интернете?",
    a: "Да. Мы проверяем это на реальных сим-картах — соединение проходит там, где обычный VPN уже не открывается.",
  },
  {
    q: "Сложно настраивать?",
    a: "Нет. Нужно одно бесплатное приложение — бот подскажет какое и поможет. Вы добавляете одну ссылку, дальше всё работает само.",
  },
  {
    q: "Как платить, если карта российская?",
    a: "Можно оплатить российской картой или криптовалютой — прямо в боте или на сайте.",
  },
  {
    q: "Есть бесплатный период?",
    a: "Да — 7 дней бесплатно, без карты и без автосписаний. Понравится — выберете тариф.",
  },
  {
    q: "Сколько устройств можно подключить?",
    a: "От 1 до 8 в зависимости от тарифа. Одна подписка работает на телефоне, ноутбуке и планшете одновременно.",
  },
];

export function Faq() {
  return (
    <section id="faq" className="section faq" aria-labelledby="faq-heading">
      <div className="container faq__inner">
        <header className="faq__head">
          <span className="eyebrow">FAQ</span>
          <h2 id="faq-heading">Частые вопросы</h2>
        </header>

        <div className="faq__list">
          {ITEMS.map((item, i) => (
            <details key={item.q} className="faq__item" name="faq" open={i === 0}>
              <summary className="faq__q">
                <span>{item.q}</span>
                <span className="faq__icon" aria-hidden />
              </summary>
              <p className="faq__a">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

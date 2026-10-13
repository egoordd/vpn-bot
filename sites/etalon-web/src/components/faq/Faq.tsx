import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./faq.css";

const QUESTIONS = [
  {
    q: "Что такое автопилот?",
    a: "Это первый пункт в списке приложения, со значком ⚡️. Он сам сверяет серверы и держит соединение на самом быстром, а если связь проседает — перестраивает маршрут без вашего участия.",
  },
  {
    q: "Будут ли работать банки и Госуслуги?",
    a: "Да. Выберите «🇷🇺 Режим РУ-сервисов» — российские сайты и приложения пойдут напрямую, а всё остальное — через VPN. Выключать VPN не придётся.",
  },
  {
    q: "Как подключиться?",
    a: "Нужно одно бесплатное приложение — Happ. Бот пришлёт ссылку на него и кнопку «Добавить в Happ», дальше всё работает само.",
  },
  {
    q: "Есть бесплатный период?",
    a: `Да — ${TRIAL_DAYS_LABEL} бесплатно, до 2 устройств, без оплаты и привязки карты.`,
  },
  {
    q: "Сколько устройств можно подключить?",
    a: "До 5 в любом тарифе. Одна ссылка подписки работает на телефоне, ноутбуке и планшете одновременно.",
  },
  {
    q: "Что делать, если перестало подключаться?",
    a: "В Happ потяните список подписки вниз, чтобы она обновилась, затем выключите и включите VPN. Не помогло — напишите в поддержку через бота.",
  },
];

export function Faq() {
  return (
    <section id="faq" className="section faq" aria-labelledby="faq-title">
      <div className="container faq__layout">
        <header className="section-head reveal">
          <span className="overline">Вопросы</span>
          <h2 id="faq-title">
            Коротко <em>о главном</em>
          </h2>
        </header>
        <div className="faq__list">
          {QUESTIONS.map((item, i) => (
            <details key={item.q} className="faq__item reveal" name="faq" open={i === 0}>
              <summary>
                <span>{item.q}</span>
                <span className="faq__icon" aria-hidden />
              </summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

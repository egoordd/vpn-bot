import "./faq.css";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";

const ITEMS = [
  {
    q: "Что такое авто-выбор сервера?",
    a: "Это первый пункт в списке приложения, со значком ⚡️. Он сам проверяет все серверы и держит соединение на самом быстром, а если сервер начнёт тормозить — переключится без вашего участия.",
  },
  {
    q: "Будут ли работать банки и Госуслуги?",
    a: "Да. Выберите «🇷🇺 Режим РУ-сервисов» — российские сайты и приложения пойдут напрямую, а всё остальное — через VPN. Выключать VPN не придётся.",
  },
  {
    q: "Сложно настраивать?",
    a: "Нет. Нужно одно бесплатное приложение — Happ. Бот пришлёт ссылку на него и кнопку «Добавить в Happ», дальше всё работает само.",
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

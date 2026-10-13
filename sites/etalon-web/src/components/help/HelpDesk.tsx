import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./help.css";

const QUESTIONS = [
  {
    q: "Что такое автопилот?",
    a: "Это первый пункт в списке приложения, со значком ⚡️. Он сам сверяет все серверы и держит соединение на самом быстром; если направление начнёт тормозить — перестроит маршрут без вашего участия.",
  },
  {
    q: "Будут ли работать банки и Госуслуги?",
    a: "Да. Выберите «🇷🇺 Режим РУ-сервисов» — российские сайты и приложения пойдут напрямую, а всё остальное — через VPN. Выключать VPN не придётся.",
  },
  {
    q: "Сложно подключиться?",
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

export function HelpDesk() {
  return (
    <section id="help" className="section help" aria-labelledby="help-title">
      <div className="container help__layout">
        <header className="section-head reveal">
          <span className="eyebrow">Справочная</span>
          <h2 id="help-title">Ответы до вылета</h2>
          <p className="lead">Не нашли ответ — бот подскажет и поможет с подключением.</p>
        </header>
        <div className="help__list">
          {QUESTIONS.map((item, i) => (
            <details key={item.q} className="help__item reveal" name="help" open={i === 0}>
              <summary>
                <span>{item.q}</span>
                <span className="help__icon" aria-hidden />
              </summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

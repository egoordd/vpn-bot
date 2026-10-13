import { Button } from "@/components/ui/Button";
import { botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./connect.css";

const STEPS = [
  {
    n: "01",
    title: "Получите доступ",
    body: `Откройте бота и нажмите «Попробовать бесплатно» — ${TRIAL_DAYS_LABEL} сразу, без оплаты.`,
  },
  {
    n: "02",
    title: "Установите Happ",
    body: "Бот пришлёт ссылку на приложение для iPhone, Android, Windows или Mac.",
  },
  {
    n: "03",
    title: "Добавьте подписку",
    body: "Одна кнопка «Добавить в Happ» — выберите пункт ⚡️ и включите VPN.",
  },
];

export function Connect() {
  return (
    <section id="connect" className="section connect" aria-labelledby="connect-title">
      <div className="container">
        <header className="section-head connect__head reveal">
          <span className="overline">Подключение</span>
          <h2 id="connect-title">
            Три касания — <em>и всё готово</em>
          </h2>
        </header>
        <ol className="connect__steps">
          {STEPS.map((s) => (
            <li key={s.n} className="connect__step reveal">
              <span className="connect__n">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </li>
          ))}
        </ol>
        <div className="connect__cta reveal">
          <Button href={botLink()}>Открыть Telegram-бота</Button>
          <span>Работает на iPhone, iPad, Android, Windows и macOS</span>
        </div>
      </div>
    </section>
  );
}

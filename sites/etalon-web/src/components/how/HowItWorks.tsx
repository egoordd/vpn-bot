import { Button } from "@/components/ui/Button";
import { botLink } from "@/lib/site";
import "./how.css";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";

const STEPS = [
  {
    n: "01",
    title: "Получите доступ в боте",
    body: `Откройте бота и нажмите «Попробовать бесплатно» — доступ на ${TRIAL_DAYS_LABEL} сразу, без оплаты и регистрации.`,
  },
  {
    n: "02",
    title: "Установите Happ",
    body: "Бот пришлёт ссылку на приложение для вашего устройства: iPhone, Android, Windows или Mac.",
  },
  {
    n: "03",
    title: "Нажмите «Добавить в Happ»",
    body: "Подписка добавится сама. Выберите первый пункт со значком ⚡️ и включите VPN — готово.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="section how" aria-labelledby="how-heading">
      <div className="container">
        <div className="how__layout">
          <header className="how__head">
            <span className="eyebrow">Три шага</span>
            <h2 id="how-heading">Подключение за одну минуту</h2>
            <p className="lead how__sub">
              Три простых шага — и вы онлайн. Ничего настраивать вручную не нужно,
              всё сделает бот.
            </p>
            <Button href={botLink()} size="lg" className="how__cta">
              Начать бесплатно
            </Button>
          </header>

          <ol className="how__steps">
            {STEPS.map((step) => (
              <li key={step.n} className="how__step">
                <span className="how__step-n mono">{step.n}</span>
                <div>
                  <h3 className="how__step-title">{step.title}</h3>
                  <p className="how__step-body">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

import { Button } from "@/components/ui/Button";
import { botLink } from "@/lib/site";
import "./how.css";

const STEPS = [
  {
    n: "01",
    title: "Запустите бота",
    body: "Нажмите «Подключить» — бот сразу даст бесплатный доступ на 3 дня. Без карты и регистрации.",
  },
  {
    n: "02",
    title: "Добавьте ссылку",
    body: "Скопируйте ссылку в приложение — бот подскажет, в какое. Дальше всё настроится само.",
  },
  {
    n: "03",
    title: "Готово",
    body: "Включаете — и пользуетесь интернетом как обычно, только без ограничений.",
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

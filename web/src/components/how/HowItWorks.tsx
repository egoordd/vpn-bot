import { Button } from "@/components/ui/Button";
import { botLink } from "@/lib/site";
import "./how.css";

const STEPS = [
  {
    n: "01",
    title: "Запустите бота",
    body: "Нажмите «Подключить», бот выдаст пробник на 7 дней — без карты и регистрации.",
  },
  {
    n: "02",
    title: "Импортируйте ссылку",
    body: "Одна ссылка-подписка для Happ, V2RayTun или Hiddify. Конфиг обновится сам.",
  },
  {
    n: "03",
    title: "Включите и забудьте",
    body: "Трафик идёт через замаскированный туннель. Скорость как у обычного соединения.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="section how" aria-labelledby="how-heading">
      <div className="container">
        <div className="how__layout">
          <header className="how__head">
            <span className="eyebrow">Три шага</span>
            <h2 id="how-heading">От нуля до защищённого трафика — за минуту</h2>
            <p className="lead how__sub">
              Никаких ручных настроек портов и ключей. Всё, что нужно, бот соберёт
              за вас.
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

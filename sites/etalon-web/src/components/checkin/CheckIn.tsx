import { Button } from "@/components/ui/Button";
import { botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./checkin.css";

const STEPS = [
  {
    gate: "01",
    title: "Получите билет в боте",
    body: `Откройте @etallonvpn_bot и нажмите «Попробовать бесплатно» — доступ на ${TRIAL_DAYS_LABEL} сразу, без оплаты.`,
  },
  {
    gate: "02",
    title: "Установите Happ",
    body: "Бот пришлёт приложение для вашего устройства: iPhone, Android, Windows или Mac.",
  },
  {
    gate: "03",
    title: "Нажмите «Добавить в Happ»",
    body: "Подписка добавится сама. Выберите пункт ⚡️, включите VPN — и взлёт.",
  },
];

export function CheckIn() {
  return (
    <section id="checkin" className="section checkin" aria-labelledby="checkin-title">
      <div className="container checkin__layout">
        <header className="section-head reveal">
          <span className="eyebrow">Онлайн-регистрация</span>
          <h2 id="checkin-title">От бота до взлёта — меньше минуты</h2>
          <p className="lead">Без очередей, анкет и настроек. Всё, что нужно, пришлёт бот.</p>
          <div>
            <Button href={botLink()} variant="gold">
              Пройти регистрацию
            </Button>
          </div>
        </header>

        <ol className="checkin__steps">
          {STEPS.map((s) => (
            <li key={s.gate} className="checkin__step reveal">
              <span className="checkin__gate">
                <span>Шаг</span>
                {s.gate}
              </span>
              <div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

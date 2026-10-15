import { SITE, botLink } from "@/lib/site";
import { TRIAL, TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { Button, Chevron } from "../ui/ui";
import "./connect.css";

const STEPS = [
  {
    title: "Откройте бота",
    text: `Нажмите «Попробовать бесплатно» в @${SITE.botUsername} — пробный период на ${TRIAL_DAYS_LABEL} выдаётся сразу, без карты.`,
  },
  {
    title: "Установите Happ",
    text: "Бот пришлёт ссылку на приложение для вашего устройства: iPhone, Android, Windows или Mac.",
  },
  {
    title: "Добавьте подписку",
    text: "Кнопка «Добавить в Happ» вставит подписку сама. Включите VPN — готово.",
  },
] as const;

const DEVICES = ["iPhone", "iPad", "Android", "Windows", "Mac"] as const;

export function Connect() {
  return (
    <section className="section connect" id="connect" aria-labelledby="connect-title">
      <div className="wrap">
        <div className="connect__panel">
          <div className="section-head connect__head">
            <span className="eyebrow">Подключение</span>
            <h2 id="connect-title">Три шага — и вы под защитой</h2>
            <p>Обычно на всё уходит меньше минуты. Если что-то не получится, поддержка в боте поможет.</p>
          </div>
          <ol className="steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="step">
                <span className="step__badge" aria-hidden="true">
                  <svg viewBox="0 0 64 44">
                    <path d="M6 38 32 12l26 26" />
                  </svg>
                  <b>{index + 1}</b>
                </span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            ))}
          </ol>
          <div className="connect__foot">
            <ul className="connect__devices" aria-label="Устройства">
              {DEVICES.map((device) => (
                <li key={device}>{device}</li>
              ))}
            </ul>
            <Button href={botLink("site")} variant="amber" size="lg" external>
              Получить {TRIAL_DAYS_LABEL} · {TRIAL.trafficGb} ГБ бесплатно <Chevron />
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

import { SITE, TOWERS } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { Tower } from "../ui/Tower";
import "./towers.css";

const STEPS = [
  {
    title: "Откройте бота",
    text: `@${SITE.botUsername} спросит язык и выдаст пробный период на ${TRIAL_DAYS_LABEL} — без карты.`,
  },
  {
    title: "Установите Happ",
    text: "Бот пришлёт ссылку на приложение для вашего устройства: iPhone, Android, Windows или Mac.",
  },
  {
    title: "Добавьте подписку",
    text: "Кнопка «Добавить в Happ» всё сделает сама. Выберите «⚡️ Авто-выбор» и включите VPN.",
  },
] as const;

export function Towers() {
  return (
    <section className="section towers" id="towers" aria-labelledby="towers-title">
      <div className="wrap">
        <div className="section-head">
          <span className="eyebrow">Башни</span>
          <h2 id="towers-title">Две страны и ворота между ними</h2>
          <p>Выходы в Германии и Нидерландах. Авто-выбор сам решает, через какую башню сейчас быстрее.</p>
        </div>
        <div className="keep">
          <article className="keep__tower">
            <Tower className="keep__icon" />
            <span className="keep__flag" aria-hidden="true">
              {TOWERS[0].flag}
            </span>
            <h3>{TOWERS[0].name}</h3>
            <p>Выход в Германии</p>
          </article>
          <div className="keep__gate">
            <span className="keep__line" aria-hidden="true">
              <i />
            </span>
            <strong>⚡️ Авто-выбор</strong>
            <p>держит самый быстрый выход и переключается сам</p>
          </div>
          <article className="keep__tower">
            <Tower className="keep__icon" />
            <span className="keep__flag" aria-hidden="true">
              {TOWERS[1].flag}
            </span>
            <h3>{TOWERS[1].name}</h3>
            <p>Выход в Нидерландах</p>
          </article>
        </div>

        <ol className="steps" aria-label="Как подключиться">
          {STEPS.map((step, index) => (
            <li key={step.title} className="step">
              <span className="step__num" aria-hidden="true">
                {["I", "II", "III"][index]}
              </span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

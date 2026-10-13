import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { botLink } from "@/lib/site";
import { PLANS, pricePerMonth, TRIAL, TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./tickets.css";

const FARES: Record<string, { fare: string; duration: string }> = {
  "1m": { fare: "Стандарт", duration: "1 месяц" },
  "3m": { fare: "Комфорт", duration: "3 месяца" },
  "6m": { fare: "Бизнес", duration: "6 месяцев" },
  "12m": { fare: "Первый класс", duration: "12 месяцев" },
};
const FIRST_CLASS = "12m";

export function Tickets() {
  return (
    <section id="tickets" className="section tickets" aria-labelledby="tickets-title">
      <div className="container">
        <header className="section-head reveal">
          <span className="eyebrow">Билеты</span>
          <h2 id="tickets-title">Чем дальше рейс — тем дешевле месяц</h2>
          <p className="lead">
            В каждом билете — все четыре направления, автопилот, режим РУ-сервисов и до 5 устройств.
          </p>
        </header>

        <div className="tickets__grid">
          {PLANS.map((plan) => {
            const { fare, duration } = FARES[plan.code];
            const first = plan.code === FIRST_CLASS;
            return (
              <article key={plan.code} className={cn("ticket reveal", first && "ticket--first")}>
                <div className="ticket__body">
                  <span className="ticket__fare">{fare}</span>
                  <h3 className="ticket__duration">{duration}</h3>
                  <p className="ticket__price">
                    {plan.priceRub.toLocaleString("ru-RU")} <span>₽</span>
                  </p>
                  <p className="ticket__per">≈ {pricePerMonth(plan)} ₽ в месяц</p>
                  <ul className="ticket__list">
                    <li>4 направления</li>
                    <li>Автопилот ⚡️</li>
                    <li>Режим РУ-сервисов</li>
                    <li>До {plan.deviceLimit} устройств</li>
                  </ul>
                </div>
                <div className="ticket__stub">
                  <Button href={botLink()} variant={first ? "gold" : "navy"} size="md" className="ticket__cta">
                    Оформить в боте
                  </Button>
                </div>
                {first && <span className="ticket__ribbon">Выгоднее всего</span>}
              </article>
            );
          })}
        </div>

        <aside className="trial reveal" aria-labelledby="trial-title">
          <div>
            <span className="trial__tag">Пробный рейс</span>
            <h3 id="trial-title">{TRIAL_DAYS_LABEL} бесплатно — без оплаты и карты</h3>
            <p>
              До {TRIAL.deviceLimit} устройств и {TRIAL.trafficGb} ГБ. Понравится — выберете билет, ссылка подписки
              останется прежней.
            </p>
          </div>
          <Button href={botLink()}>Открыть бота</Button>
        </aside>
      </div>
    </section>
  );
}

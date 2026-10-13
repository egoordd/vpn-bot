import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { cn } from "@/lib/cn";
import { formatRubFromRubles } from "@/lib/money";
import { botLink } from "@/lib/site";
import { PLANS, pricePerMonth, TRIAL, TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./pricing.css";

const RECOMMENDED = new Set(["12m"]);

const DURATION_LABELS: Record<number, string> = { 30: "1 месяц", 90: "3 месяца", 180: "6 месяцев", 365: "12 месяцев" };

function durationLabel(days: number): string {
  return DURATION_LABELS[days] ?? `${Math.round(days / 30)} мес`;
}

export function Pricing() {
  return (
    <section id="pricing" className="section pricing" aria-labelledby="pricing-heading">
      <div className="container">
        <header className="pricing__head">
          <span className="eyebrow">Тарифы</span>
          <h2 id="pricing-heading">Чем дольше срок, тем дешевле месяц</h2>
          <p className="lead pricing__sub">
            Во всех тарифах — четыре страны, авто-выбор сервера и режим РУ-сервисов. Пробный период
            на {TRIAL_DAYS_LABEL} доступен всем и бесплатно.
          </p>
        </header>

        <div className="pricing__grid">
          {PLANS.map((plan) => {
            const recommended = RECOMMENDED.has(plan.code);
            return (
              <article key={plan.code} className={cn("plan", recommended && "plan--featured")}>
                {recommended && (
                  <Pill tone="accent" className="plan__badge">
                    Выгоднее всего
                  </Pill>
                )}
                <h3 className="plan__duration">{durationLabel(plan.durationDays)}</h3>
                <p className="plan__price">
                  <span className="plan__price-value">{formatRubFromRubles(plan.priceRub)}</span>
                  <span className="plan__price-per mono">≈ {pricePerMonth(plan)} ₽/мес</span>
                </p>

                <ul className="plan__features">
                  <li>
                    <Dot /> До {plan.deviceLimit} устройств
                  </li>
                  <li>
                    <Dot /> 4 страны в одной подписке
                  </li>
                  <li>
                    <Dot /> Авто-выбор сервера
                  </li>
                  <li>
                    <Dot /> Режим РУ-сервисов
                  </li>
                </ul>

                <Button href={botLink()} variant={recommended ? "primary" : "ghost"} className="plan__cta">
                  Оформить в боте
                </Button>
              </article>
            );
          })}
        </div>

        <aside className="pricing__trial" aria-labelledby="trial-heading">
          <div className="pricing__trial-text">
            <Pill tone="accent" live>
              Бесплатно
            </Pill>
            <h3 id="trial-heading" className="pricing__trial-title">
              Сначала попробовать: {TRIAL_DAYS_LABEL} в Telegram-боте
            </h3>
            <p className="pricing__trial-sub">
              Пробный период выдаёт бот: до {TRIAL.deviceLimit} устройств и {TRIAL.trafficGb} ГБ, оплата и карта
              не нужны. Там же будет ваша ссылка-подписка, если решите остаться.
            </p>
          </div>
          <Button href={botLink()} size="lg" className="pricing__trial-cta">
            Открыть Telegram-бота
          </Button>
        </aside>
      </div>
    </section>
  );
}

function Dot() {
  return <span className="plan__dot" aria-hidden />;
}

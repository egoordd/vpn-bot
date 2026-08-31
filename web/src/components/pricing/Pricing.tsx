"use client";

import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { cn } from "@/lib/cn";
import { formatRubFromRubles } from "@/lib/money";
import { botLink } from "@/lib/site";
import { pricePerMonth, tariffsByTier, trafficLabel, TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./pricing.css";

const RECOMMENDED = new Set(["standard_3m"]);

function durationLabel(days: number): string {
  if (days >= 365) return "12 месяцев";
  return `${Math.round(days / 30)} мес`;
}

export function Pricing() {
  const plans = tariffsByTier("standard");

  return (
    <section id="pricing" className="section pricing" aria-labelledby="pricing-heading">
      <div className="container">
        <header className="pricing__head">
          <span className="eyebrow">Тарифы</span>
          <h2 id="pricing-heading">Чем дольше срок, тем дешевле месяц</h2>
          <p className="lead pricing__sub">
            Чем длиннее срок — тем дешевле месяц. Пробник на {TRIAL_DAYS_LABEL}
            доступен всем и бесплатно.
          </p>
        </header>

        <div className="pricing__grid">
          {plans.map((plan) => {
            const recommended = RECOMMENDED.has(plan.code);
            return (
              <article
                key={plan.code}
                className={cn("plan", recommended && "plan--featured")}
              >
                {recommended && (
                  <Pill tone="accent" className="plan__badge">
                    Выгодно
                  </Pill>
                )}
                <h3 className="plan__duration">{durationLabel(plan.durationDays)}</h3>
                <p className="plan__price">
                  <span className="plan__price-value">{formatRubFromRubles(plan.priceRub)}</span>
                  <span className="plan__price-per mono">≈ {pricePerMonth(plan)} ₽/мес</span>
                </p>

                <ul className="plan__features">
                  <li>
                    <Dot /> {trafficLabel(plan)}
                  </li>
                  <li>
                    <Dot /> До {plan.deviceLimit} устройств
                  </li>
                  <li>
                    <Dot /> Все локации в одной подписке
                  </li>
                  <li>
                    <Dot /> Ссылка-подписка + авто-обновление
                  </li>
                </ul>

                <Button
                  href={`/buy?plan=${plan.code}`}
                  variant={recommended ? "primary" : "ghost"}
                  className="plan__cta"
                >
                  {"Купить"}
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
              Пробный период выдаёт бот — оплата и карта для него не нужны. Там же будет ваша
              ссылка-подписка, если решите остаться.
            </p>
          </div>
          <Button href={botLink()} size="lg" className="pricing__trial-cta">
            Открыть Telegram-бота
          </Button>
        </aside>

        <p className="pricing__foot mono">
          Нужен выделенный сервер только под вас? Тариф Dedicated — скоро.
        </p>
      </div>
    </section>
  );
}

function Dot() {
  return <span className="plan__dot" aria-hidden />;
}

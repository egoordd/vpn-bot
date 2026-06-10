"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { cn } from "@/lib/cn";
import { formatRubFromRubles } from "@/lib/money";
import { botLink } from "@/lib/site";
import { type Tier, pricePerMonth, tariffsByTier } from "@/lib/tariffs";
import "./pricing.css";

const RECOMMENDED = new Set(["standard_3m", "premium_3m"]);

const TIER_META: Record<"standard" | "premium", { label: string; note: string }> = {
  standard: { label: "Standard", note: "Общий пул нод — лучшая цена" },
  premium: { label: "Premium", note: "Меньше соседей, выбор локации" },
};

function durationLabel(days: number): string {
  if (days >= 365) return "12 месяцев";
  return `${Math.round(days / 30)} мес`;
}

export function Pricing() {
  const [tier, setTier] = useState<"standard" | "premium">("standard");
  const plans = tariffsByTier(tier as Tier);

  return (
    <section id="pricing" className="section pricing" aria-labelledby="pricing-heading">
      <div className="container">
        <header className="pricing__head">
          <span className="eyebrow">Тарифы</span>
          <h2 id="pricing-heading">Платите за плотность, а не за обещания</h2>
          <p className="lead pricing__sub">
            Чем выше тариф — тем меньше людей на ноде и стабильнее скорость.
            Пробник на 7 дней доступен всем и бесплатно.
          </p>

          <div className="pricing__toggle" role="tablist" aria-label="Уровень тарифа">
            {(["standard", "premium"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tier === t}
                className={cn("pricing__toggle-btn", tier === t && "is-active")}
                onClick={() => setTier(t)}
              >
                {TIER_META[t].label}
              </button>
            ))}
          </div>
          <p className="pricing__toggle-note mono">{TIER_META[tier].note}</p>
        </header>

        <div className="pricing__grid">
          {plans.map((plan) => {
            const recommended = RECOMMENDED.has(plan.code);
            return (
              <article
                key={plan.code}
                className={cn("plan", recommended && "plan--featured", tier === "premium" && "plan--premium")}
              >
                {recommended && (
                  <Pill tone={tier === "premium" ? "premium" : "accent"} className="plan__badge">
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
                    <Dot /> {plan.trafficGb} ГБ трафика
                  </li>
                  <li>
                    <Dot /> До {plan.deviceLimit} устройств
                  </li>
                  <li>
                    <Dot /> {tier === "premium" ? "Выбор локации" : "Общий пул локаций"}
                  </li>
                  <li>
                    <Dot /> Ссылка-подписка + авто-обновление
                  </li>
                </ul>

                <Button
                  href={botLink(`buy_${plan.code}`)}
                  variant={recommended ? (tier === "premium" ? "premium" : "primary") : "ghost"}
                  className="plan__cta"
                >
                  Выбрать
                </Button>
              </article>
            );
          })}
        </div>

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

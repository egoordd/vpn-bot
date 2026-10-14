import { Button } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/LogoMark";
import { cn } from "@/lib/cn";
import { botLink } from "@/lib/site";
import { PLANS, pricePerMonth, savingPercent, TRIAL, TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import "./pricing.css";

const LABELS: Record<string, string> = { "1m": "1 месяц", "3m": "3 месяца", "6m": "6 месяцев", "12m": "12 месяцев" };
const SIGNATURE = "12m";

export function Pricing() {
  return (
    <section id="pricing" className="section pricing" aria-labelledby="pricing-title">
      <div className="container">
        <header className="section-head pricing__head reveal">
          <span className="overline">Тарифы</span>
          <h2 id="pricing-title">
            Одна подписка. <em>Без мелкого шрифта.</em>
          </h2>
          <p className="lead">
            В каждом тарифе — все четыре страны, автопилот, режим РУ-сервисов и до 5 устройств.
          </p>
        </header>

        <div className="plans">
          {PLANS.map((plan) => {
            const signature = plan.code === SIGNATURE;
            const saving = savingPercent(plan);
            return (
              <article key={plan.code} className={cn("plan reveal", signature && "plan--signature")}>
                {signature && (
                  <span className="plan__badge">
                    <LogoMark className="plan__badge-key" /> Эталон
                  </span>
                )}
                <h3 className="plan__term">{LABELS[plan.code]}</h3>
                <p className="plan__price">
                  {plan.priceRub.toLocaleString("ru-RU")}
                  <span>₽</span>
                </p>
                <p className="plan__per">
                  {pricePerMonth(plan)} ₽ в месяц
                  {saving > 0 && <span className="plan__save">−{saving}%</span>}
                </p>
                <Button href={`/checkout/?plan=${plan.code}`} variant={signature ? "gold" : "outline"} className="plan__cta">
                  Выбрать
                </Button>
              </article>
            );
          })}
        </div>

        <p className="pricing__trial reveal">
          <span>Пробный период</span> {TRIAL_DAYS_LABEL} бесплатно · до {TRIAL.deviceLimit} устройств · без карты —{" "}
          <a href={botLink()} target="_blank" rel="noopener noreferrer">
            начать в боте
          </a>
        </p>
        <p className="pricing__docs reveal">
          <a href="/tariffs/">Подробно о тарифах и оплате</a>
          <a href="/terms/#refund">Условия возврата</a>
        </p>
      </div>
    </section>
  );
}

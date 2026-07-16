import { Button } from "@/components/ui/Button";
import { TrialButton } from "./TrialButton";
import { Pill } from "@/components/ui/Pill";
import { formatDate, formatGb, daysLeft, trafficPercent } from "@/lib/format";
import { botLink } from "@/lib/site";
import type { SubscriptionSnapshot } from "@/lib/billing/types";
import "./subscription-card.css";

export function SubscriptionCard({ sub }: { sub: SubscriptionSnapshot }) {
  if (!sub.exists) {
    return (
      <article className="card card--span2 sub">
        <div className="card__head">
          <span className="card__title">Подписка</span>
          <Pill tone="warn">нет активной</Pill>
        </div>
        <p className="sub__empty">У вас пока нет подписки. Активируйте пробный период на 3 дня — без карты.</p>
        <TrialButton />
      </article>
    );
  }

  const left = daysLeft(sub.expiresAt);
  const pct = trafficPercent(sub.trafficUsedBytes, sub.trafficLimitBytes);
  const isPremium = sub.tier === "premium";
  const expiringSoon = left !== null && left <= 5;

  return (
    <article className="card card--span2 sub">
      <div className="card__head">
        <span className="card__title">Подписка</span>
        <Pill tone={sub.isActive ? "accent" : "danger"} live={sub.isActive}>
          {sub.isActive ? "активна" : "неактивна"}
        </Pill>
      </div>

      <div className="sub__top">
        <div>
          <h3 className="sub__plan">{sub.planTitle}</h3>
          <p className="sub__meta">
            {isPremium ? <Pill tone="premium">Premium</Pill> : <Pill tone="neutral">Standard</Pill>}
            <span className="mono sub__devices">до {sub.deviceLimit} устройств</span>
          </p>
        </div>
        <div className="sub__expiry">
          <span className="sub__expiry-label">Действует до</span>
          <span className="sub__expiry-date">{formatDate(sub.expiresAt)}</span>
          {left !== null && (
            <span className={`mono sub__expiry-days ${expiringSoon ? "is-soon" : ""}`}>
              осталось {left} дн.
            </span>
          )}
        </div>
      </div>

      <div className="sub__traffic">
        <div className="sub__traffic-row">
          <span className="mono">
            {formatGb(sub.trafficUsedBytes)} / {formatGb(sub.trafficLimitBytes)}
          </span>
          <span className="mono sub__traffic-pct">{pct}%</span>
        </div>
        <div className="sub__bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <span className={`sub__bar-fill ${pct >= 90 ? "is-high" : ""}`} style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="sub__actions">
        <Button href={botLink(`buy_${sub.plan}`)}>Продлить</Button>
        <Button href={botLink()} variant="ghost">
          Сменить тариф
        </Button>
      </div>
    </article>
  );
}

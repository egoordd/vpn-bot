import { CopyButton } from "@/components/ui/CopyButton";
import { formatRub } from "@/lib/money";
import { botLink } from "@/lib/site";
import type { ReferralStats } from "@/lib/billing/types";
import "./referral-card.css";

export function ReferralCard({ referral }: { referral: ReferralStats }) {
  const link = referral.refCode ? botLink(`ref_${referral.refCode}`) : botLink();

  return (
    <article className="card referral">
      <div className="card__head">
        <span className="card__title">Реферальная программа</span>
      </div>

      <p className="referral__lead">
        Делитесь ссылкой — получаете <strong>{referral.rewardPercent}%</strong> с каждой оплаты
        приглашённого на свой баланс.
      </p>

      <div className="referral__link">
        <code className="referral__url mono">{link}</code>
        <CopyButton value={link} label="Скопировать" />
      </div>

      <dl className="referral__stats">
        <div>
          <dt>Приглашено</dt>
          <dd>{referral.referralsCount}</dd>
        </div>
        <div>
          <dt>Заработано</dt>
          <dd className="referral__earned">{formatRub(referral.totalEarnedKopecks)}</dd>
        </div>
        <div>
          <dt>Ставка</dt>
          <dd>{referral.rewardPercent}%</dd>
        </div>
      </dl>
    </article>
  );
}

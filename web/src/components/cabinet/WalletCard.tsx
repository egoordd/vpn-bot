import { Button } from "@/components/ui/Button";
import { formatRub } from "@/lib/money";
import { formatRelative } from "@/lib/format";
import { botLink } from "@/lib/site";
import type { WalletEntry, WalletSnapshot } from "@/lib/billing/types";
import "./wallet-card.css";

const KIND_LABEL: Record<WalletEntry["kind"], string> = {
  deposit: "Пополнение",
  spend: "Списание",
  referral_reward: "Реферал",
  promo_bonus: "Промокод",
  refund: "Возврат",
  adjustment: "Коррекция",
};

export function WalletCard({ wallet, balanceDisplay }: { wallet: WalletSnapshot; balanceDisplay: string }) {
  return (
    <article className="card wallet">
      <div className="card__head">
        <span className="card__title">Кошелёк</span>
        <Button href={botLink("topup")} variant="ghost" className="wallet__topup">
          Пополнить
        </Button>
      </div>

      <p className="wallet__balance">
        <span className="wallet__balance-value">{balanceDisplay}</span>
        <span className="wallet__balance-note mono">доступно к оплате тарифов</span>
      </p>

      <ul className="wallet__list">
        {wallet.entries.slice(0, 5).map((entry) => {
          const positive = entry.amountKopecks >= 0;
          return (
            <li key={entry.id} className="wallet__item">
              <span className={`wallet__kind wallet__kind--${entry.kind}`}>{KIND_LABEL[entry.kind]}</span>
              <span className="wallet__desc">{entry.description ?? "—"}</span>
              <span className="wallet__time mono">{formatRelative(entry.createdAt)}</span>
              <span className={`wallet__amount mono ${positive ? "is-plus" : "is-minus"}`}>
                {positive ? "+" : "−"}
                {formatRub(Math.abs(entry.amountKopecks))}
              </span>
            </li>
          );
        })}
        {wallet.entries.length === 0 && <li className="wallet__empty">Операций пока нет.</li>}
      </ul>
    </article>
  );
}

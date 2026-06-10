import type { AccountOverview } from "@/lib/billing/types";
import { ConnectCard } from "./ConnectCard";
import { PromoCard } from "./PromoCard";
import { ReferralCard } from "./ReferralCard";
import { SubscriptionCard } from "./SubscriptionCard";
import { WalletCard } from "./WalletCard";
import "./cabinet.css";

export function CabinetCards({ account }: { account: AccountOverview }) {
  return (
    <div className="cab__grid">
      <SubscriptionCard sub={account.subscription} />
      <WalletCard wallet={account.wallet} balanceDisplay={account.balanceDisplay} />
      <ReferralCard referral={account.referral} />
      <PromoCard />
      <ConnectCard subscriptionUrl={account.subscription.subscriptionUrl} />
    </div>
  );
}

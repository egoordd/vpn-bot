import type { AccountOverview } from "@/lib/billing/types";
import { ConnectCard } from "./ConnectCard";
import { EmailCard } from "./EmailCard";
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
      <EmailCard email={account.email ?? null} />
      <ConnectCard subscriptionUrl={account.subscription.subscriptionUrl} />
    </div>
  );
}

import type { AccountOverview } from "@/lib/billing/types";
import { ConnectCard } from "./ConnectCard";
import { EmailCard } from "./EmailCard";
import { PasswordCard } from "./PasswordCard";
import { PromoCard } from "./PromoCard";
import { SubscriptionCard } from "./SubscriptionCard";
import "./cabinet.css";

export function CabinetCards({ account }: { account: AccountOverview }) {
  return (
    <div className="cab__grid">
      <SubscriptionCard sub={account.subscription} />
      <PromoCard />
      <EmailCard email={account.email ?? null} />
      {/* Отрицательный id — аккаунт сайта с входом по почте и паролю. */}
      {account.telegramId < 0 && <PasswordCard />}
      <ConnectCard subscriptionUrl={account.subscription.subscriptionUrl} />
    </div>
  );
}

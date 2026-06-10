/**
 * Billing DTOs — the site's view of `services/billing_api.py`.
 * Field names mirror the Python dataclasses (snake → camel) so the HTTP
 * mapping is mechanical when the real API is wired.
 */
export interface SubscriptionSnapshot {
  exists: boolean;
  isActive: boolean;
  plan: string | null;
  planTitle: string | null;
  tier: string | null;
  subscriptionUrl: string | null;
  trafficLimitBytes: number | null;
  trafficUsedBytes: number | null;
  deviceLimit: number | null;
  status: string | null;
  expiresAt: string | null; // ISO 8601
}

export type WalletEntryKind =
  | "deposit"
  | "spend"
  | "referral_reward"
  | "promo_bonus"
  | "refund"
  | "adjustment";

export interface WalletEntry {
  id: number;
  amountKopecks: number;
  balanceAfterKopecks: number;
  kind: WalletEntryKind;
  description: string | null;
  createdAt: string; // ISO 8601
}

export interface WalletSnapshot {
  balanceKopecks: number;
  entries: WalletEntry[];
}

export interface ReferralStats {
  refCode: string | null;
  rewardPercent: number;
  referralsCount: number;
  totalEarnedKopecks: number;
}

export interface AccountOverview {
  userId: number;
  telegramId: number;
  subscription: SubscriptionSnapshot;
  wallet: WalletSnapshot;
  balanceDisplay: string;
  referral: ReferralStats;
}

export interface DiscountResult {
  code: string;
  originalKopecks: number;
  discountKopecks: number;
  finalKopecks: number;
}

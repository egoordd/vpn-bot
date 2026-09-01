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

export interface ReferralStats {
  refCode: string | null;
  referralsCount: number;
}

export interface AccountOverview {
  userId: number;
  telegramId: number;
  subscription: SubscriptionSnapshot;
  referral: ReferralStats;
  email?: string | null;
}

export interface BillingPlanDto {
  code: string;
  title: string;
  tier: "trial" | "standard";
  durationDays: number;
  priceRub: number;
  cryptoAmount: string;
  trafficLimitBytes: number | null;
  deviceLimit: number | null;
  description: string;
}

export interface DiscountResult {
  code: string;
  originalKopecks: number;
  discountKopecks: number;
  finalKopecks: number;
}

export interface CheckoutResult {
  orderId: string;
  payUrl: string;
}

export interface WebOrderSubscription {
  subscriptionUrl: string | null;
  planTitle: string | null;
  expiresAt: string | null; // ISO 8601
  isActive: boolean;
}

export interface WebOrderStatus {
  status: "pending" | "succeeded";
  subscription?: WebOrderSubscription;
}

/** What redeeming a promo actually did. */
export interface PromoRedemption {
  code: string;
  kind: string;
  grantedDays: number | null;
}

/** Why a promo could not be redeemed — one reason per case, never a lump. */
export type PromoFailure =
  | "promo_not_found"
  | "promo_expired"
  | "promo_inactive"
  | "promo_exhausted"
  | "promo_user_limit"
  | "promo_min_amount"
  | "promo_wrong_type"
  | "unauthorized"
  | "unavailable";

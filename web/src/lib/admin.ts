import "server-only";

import crypto from "node:crypto";

export interface AdminStats {
  users: { total: number; new24h: number; new7d: number };
  subscriptions: {
    activeByTier: Record<string, number>;
    activeTotal: number;
    total: number;
  };
  money: { balancesKopecks: number; depositsKopecks: number };
  recent: AdminRecentSubscription[];
  generatedAt: string;
}

export interface AdminRecentSubscription {
  id: number;
  tier: string;
  plan: string;
  planTitle: string;
  telegramId: number;
  username: string | null;
  isActive: boolean;
  startedAt: string | null;
  expiresAt: string | null;
}

/** Opaque session value stored in the admin cookie (never the raw password). */
export function adminSessionToken(): string {
  const password = process.env.ADMIN_PASSWORD ?? "";
  return crypto.createHash("sha256").update(`unlock-admin:${password}`).digest("hex");
}

export function isAdminPassword(candidate: string): boolean {
  const expected = process.env.ADMIN_PASSWORD ?? "";
  return expected.length > 0 && candidate === expected;
}

export async function fetchAdminStats(): Promise<AdminStats | null> {
  const base = process.env.ADMIN_API_URL;
  const token = process.env.ADMIN_API_TOKEN;
  if (!base || !token) return null;
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}/admin/stats`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as AdminStats;
  } catch {
    return null;
  }
}

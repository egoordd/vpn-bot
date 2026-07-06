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

export const ADMIN_SESSION_TTL_SECONDS = 60 * 60 * 12;

/**
 * HMAC key for session tokens. Prefers ADMIN_SESSION_SECRET; falls back to a
 * key derived from ADMIN_PASSWORD so rotating the password revokes sessions.
 */
function sessionKey(): Buffer | null {
  const secret = process.env.ADMIN_SESSION_SECRET ?? "";
  if (secret.length > 0) return crypto.createHash("sha256").update(secret).digest();
  const password = process.env.ADMIN_PASSWORD ?? "";
  if (password.length === 0) return null;
  return crypto.createHash("sha256").update(`unlock-admin-session:${password}`).digest();
}

function signPayload(key: Buffer, payload: string): string {
  return crypto.createHmac("sha256", key).update(payload).digest("hex");
}

/** Random, expiring, HMAC-signed session token: `<expiresAtMs>.<nonce>.<sig>`. */
export function createAdminSession(): string | null {
  const key = sessionKey();
  if (!key) return null;
  const expiresAt = Date.now() + ADMIN_SESSION_TTL_SECONDS * 1000;
  const payload = `${expiresAt}.${crypto.randomBytes(16).toString("hex")}`;
  return `${payload}.${signPayload(key, payload)}`;
}

export function isValidAdminSession(token: string | undefined): boolean {
  if (!token) return false;
  const key = sessionKey();
  if (!key) return false;
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const [expiresAtRaw, nonce, sig] = parts;
  const expiresAt = Number(expiresAtRaw);
  if (!Number.isFinite(expiresAt) || Date.now() > expiresAt) return false;
  const expected = signPayload(key, `${expiresAtRaw}.${nonce}`);
  const sigBuf = Buffer.from(sig);
  const expectedBuf = Buffer.from(expected);
  return sigBuf.length === expectedBuf.length && crypto.timingSafeEqual(sigBuf, expectedBuf);
}

export function isAdminPassword(candidate: string): boolean {
  const expected = process.env.ADMIN_PASSWORD ?? "";
  if (expected.length === 0) return false;
  const candidateDigest = crypto.createHash("sha256").update(candidate).digest();
  const expectedDigest = crypto.createHash("sha256").update(expected).digest();
  return crypto.timingSafeEqual(candidateDigest, expectedDigest);
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

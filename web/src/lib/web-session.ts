import "server-only";

import crypto from "node:crypto";

/**
 * Cabinet session for site visitors who logged in via Telegram.
 * Token: `<telegramId>.<expiresAtMs>.<nonce>.<hmac>` — HMAC-SHA256 over the
 * first three parts, keyed by WEB_SESSION_SECRET (falls back to a key derived
 * from BOT_TOKEN, so rotating the bot token revokes web sessions too).
 */
export const USER_SESSION_COOKIE = "ulk_session";
export const USER_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60;

function sessionKey(): Buffer | null {
  const secret = process.env.WEB_SESSION_SECRET ?? "";
  if (secret.length > 0) return crypto.createHash("sha256").update(secret).digest();
  const botToken = process.env.BOT_TOKEN ?? "";
  if (botToken.length === 0) return null;
  return crypto.createHash("sha256").update(`unlock-web-session:${botToken}`).digest();
}

function sign(key: Buffer, payload: string): string {
  return crypto.createHmac("sha256", key).update(payload).digest("hex");
}

export function createUserSession(telegramId: number): string | null {
  if (!Number.isInteger(telegramId) || telegramId <= 0) return null;
  const key = sessionKey();
  if (!key) return null;
  const expiresAt = Date.now() + USER_SESSION_TTL_SECONDS * 1000;
  const payload = `${telegramId}.${expiresAt}.${crypto.randomBytes(12).toString("hex")}`;
  return `${payload}.${sign(key, payload)}`;
}

export function verifyUserSession(token: string | undefined): number | null {
  if (!token) return null;
  const key = sessionKey();
  if (!key) return null;

  const parts = token.split(".");
  if (parts.length !== 4) return null;
  const [telegramIdRaw, expiresAtRaw, nonce, mac] = parts;
  const payload = `${telegramIdRaw}.${expiresAtRaw}.${nonce}`;

  const expected = Buffer.from(sign(key, payload), "hex");
  let given: Buffer;
  try {
    given = Buffer.from(mac, "hex");
  } catch {
    return null;
  }
  if (expected.length !== given.length || !crypto.timingSafeEqual(expected, given)) {
    return null;
  }

  const expiresAt = Number(expiresAtRaw);
  if (!Number.isFinite(expiresAt) || Date.now() > expiresAt) return null;

  const telegramId = Number(telegramIdRaw);
  return Number.isInteger(telegramId) && telegramId > 0 ? telegramId : null;
}

import "server-only";

import crypto from "node:crypto";

import { NextResponse } from "next/server";

import { getSessionStamp } from "@/lib/billing/client";

/**
 * Cabinet session for site visitors who logged in via Telegram.
 * Token: `<telegramId>.<expiresAtMs>.<nonce>.<stamp>.<hmac>` — HMAC-SHA256 over
 * the first four parts, keyed by WEB_SESSION_SECRET (falls back to a key derived
 * from BOT_TOKEN, so rotating the bot token revokes web sessions too).
 *
 * `stamp` — отметка входа из биллинга. Она меняется со сменой или
 * восстановлением пароля и с «выйти на всех устройствах», и каждая проверка
 * сверяет её с биллингом: украденная сессия гаснет, как только владелец сменил
 * пароль (аудит 22.09.2026, SEC-04). Биллинг недоступен — сессия не принимается.
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

export async function createUserSession(telegramId: number): Promise<string | null> {
  // Positive ids = Telegram accounts; negative = site email/password accounts.
  // Only a zero id is invalid.
  if (!Number.isInteger(telegramId) || telegramId === 0) return null;
  const key = sessionKey();
  if (!key) return null;
  const stamp = await getSessionStamp(telegramId);
  if (!stamp) return null;
  const expiresAt = Date.now() + USER_SESSION_TTL_SECONDS * 1000;
  const payload = `${telegramId}.${expiresAt}.${crypto.randomBytes(12).toString("hex")}.${stamp}`;
  return `${payload}.${sign(key, payload)}`;
}

export async function verifyUserSession(token: string | undefined): Promise<number | null> {
  if (!token) return null;
  const key = sessionKey();
  if (!key) return null;

  const parts = token.split(".");
  if (parts.length !== 5) return null;
  const [telegramIdRaw, expiresAtRaw, nonce, stamp, mac] = parts;
  const payload = `${telegramIdRaw}.${expiresAtRaw}.${nonce}.${stamp}`;

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
  if (!Number.isInteger(telegramId) || telegramId === 0) return null;
  return (await getSessionStamp(telegramId)) === stamp ? telegramId : null;
}

/** JSON-ответ, который заодно входит в кабинет: ставит куку сессии. */
export async function signedInResponse(telegramId: number, body: Record<string, unknown> = { ok: true }) {
  const session = await createUserSession(telegramId);
  if (!session) return NextResponse.json({ error: "auth_not_configured" }, { status: 503 });
  const response = NextResponse.json(body);
  response.cookies.set(USER_SESSION_COOKIE, session, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: USER_SESSION_TTL_SECONDS,
  });
  return response;
}

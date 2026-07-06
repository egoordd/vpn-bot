import crypto from "crypto";

/**
 * Verify a Telegram Mini App `initData` string and return the authenticated
 * Telegram user id. This is the ONLY trustworthy way to know who is calling —
 * never trust a client-supplied user id (that is an IDOR).
 *
 * Algorithm (per Telegram docs): the check hash is HMAC-SHA256 of the sorted
 * `key=value` data-check-string, keyed by HMAC-SHA256("WebAppData", botToken).
 *
 * Returns the telegram user id on success, or null if the signature is invalid,
 * expired, or the bot token is not configured.
 */
export function verifyTelegramInitData(
  initData: string,
  botToken = process.env.BOT_TOKEN ?? "",
  maxAgeSeconds = 24 * 60 * 60,
): number | null {
  if (!botToken || !initData) return null;

  let params: URLSearchParams;
  try {
    params = new URLSearchParams(initData);
  } catch {
    return null;
  }

  const hash = params.get("hash");
  if (!hash) return null;

  const pairs: string[] = [];
  params.forEach((value, key) => {
    if (key !== "hash") pairs.push(`${key}=${value}`);
  });
  pairs.sort();
  const dataCheckString = pairs.join("\n");

  const secretKey = crypto.createHmac("sha256", "WebAppData").update(botToken).digest();
  const computed = crypto.createHmac("sha256", secretKey).update(dataCheckString).digest("hex");

  // Constant-time comparison.
  const a = Buffer.from(computed, "hex");
  const b = Buffer.from(hash, "hex");
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;

  // Reject stale initData to limit replay.
  const authDate = Number(params.get("auth_date") ?? "0");
  if (!authDate || Date.now() / 1000 - authDate > maxAgeSeconds) return null;

  try {
    const user = JSON.parse(params.get("user") ?? "null");
    const id = Number(user?.id);
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

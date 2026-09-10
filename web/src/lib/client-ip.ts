import crypto from "node:crypto";

/**
 * The visitor's address, as far as rate limits are concerned.
 *
 * Russian mobile networks cut Cloudflare, so the site is fronted by a relay on
 * a VPN node, and Vercel overwrites X-Forwarded-For with the relay's address:
 * every visitor would land in one rate-limit bucket and a busy evening would
 * lock everybody out. The relay passes the real address in X-Relay-Client-IP.
 * It is trusted only alongside the shared secret, so a caller reaching Vercel
 * directly cannot pick an address to hide behind.
 */
export function clientIpFrom(request: Request): string | undefined {
  const relayed = request.headers.get("x-relay-client-ip")?.trim();
  if (relayed && relayVouches(request.headers.get("x-relay-secret"))) {
    return relayed;
  }
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || undefined;
}

function relayVouches(given: string | null): boolean {
  const secret = process.env.RELAY_SECRET;
  if (!secret || !given) return false;
  const expected = Buffer.from(secret);
  const candidate = Buffer.from(given);
  return expected.length === candidate.length && crypto.timingSafeEqual(expected, candidate);
}

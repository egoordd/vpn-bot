import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { redeemPromo } from "@/lib/billing/client";
import { USER_SESSION_COOKIE, verifyUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

/**
 * Redeem a promo code for the logged-in account.
 *
 * This route used to preview a *discount* against a hardcoded user id of 1 —
 * a real account, so per-user limits were checked against the wrong person —
 * and every code we actually sell grants a subscription
 * rather than discounting a checkout. The result was that valid codes came
 * back as "промокод не найден". Redemption needs a real identity, so the
 * session decides who is calling; a client-supplied id would be an IDOR.
 */
export async function POST(request: Request) {
  const telegramId = verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value);
  if (!telegramId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let body: { code?: unknown };
  try {
    body = (await request.json()) as { code?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const code = typeof body.code === "string" ? body.code.trim() : "";
  if (!code || code.length > 64) {
    return NextResponse.json({ error: "invalid_code" }, { status: 400 });
  }

  const outcome = await redeemPromo(telegramId, code);
  if (!outcome.ok) {
    return NextResponse.json({ error: outcome.error }, { status: 400 });
  }
  return NextResponse.json({ result: outcome.result });
}

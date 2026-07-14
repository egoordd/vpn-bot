import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { CheckoutError, createWebCheckout } from "@/lib/billing/client";
import { USER_SESSION_COOKIE, verifyUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * Start a card payment from the site. Identity: the signed Telegram session
 * cookie when present, otherwise a buyer email (delivery happens on the
 * /pay/success page). The billing API is called server-side with the shared
 * bearer token — the browser never sees it.
 */
export async function POST(request: Request) {
  let body: { plan?: unknown; email?: unknown };
  try {
    body = (await request.json()) as { plan?: unknown; email?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const plan = typeof body.plan === "string" ? body.plan.trim() : "";
  if (!plan || plan.length > 64) {
    return NextResponse.json({ error: "invalid_plan" }, { status: 400 });
  }

  const telegramId = verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value) ?? undefined;
  const email =
    typeof body.email === "string" && body.email.trim() ? body.email.trim().toLowerCase() : undefined;

  if (!telegramId && !email) {
    return NextResponse.json({ error: "identity_required" }, { status: 400 });
  }
  if (email && (!EMAIL_RE.test(email) || email.length > 320)) {
    return NextResponse.json({ error: "invalid_email" }, { status: 400 });
  }

  const clientIp = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || undefined;

  try {
    const result = await createWebCheckout({ plan, telegramId, email, clientIp });
    return NextResponse.json(result);
  } catch (error: unknown) {
    if (error instanceof CheckoutError) {
      if (error.code === "rate_limited") {
        return NextResponse.json({ error: "rate_limited" }, { status: 429 });
      }
      const status = error.code === "unknown_plan" ? 404 : 502;
      return NextResponse.json({ error: error.code }, { status });
    }
    return NextResponse.json({ error: "checkout_failed" }, { status: 502 });
  }
}

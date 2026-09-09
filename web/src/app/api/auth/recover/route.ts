import { NextResponse } from "next/server";

import { WebAuthError, recoverWebAccount } from "@/lib/billing/client";
import { USER_SESSION_COOKIE, USER_SESSION_TTL_SECONDS, createUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * Set a password on the account behind a subscription link, then sign in.
 *
 * Half of the people who bought here checked out as guests: they hold an
 * account with no password, cannot sign in, and registering with their own
 * address is refused — an address is public, so accepting one would hand the
 * account to whoever guesses it. The subscription link is the proof they do
 * hold, and one use of it buys a durable password.
 */
export async function POST(request: Request) {
  let body: { subscription?: unknown; password?: unknown; email?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const subscription = typeof body.subscription === "string" ? body.subscription.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (!subscription || !password) {
    return NextResponse.json({ error: "invalid_subscription" }, { status: 400 });
  }
  if (email && !EMAIL_RE.test(email)) {
    return NextResponse.json({ error: "invalid_email" }, { status: 400 });
  }

  let telegramId: number;
  try {
    const clientIp = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || undefined;
    telegramId = await recoverWebAccount(subscription, password, email || undefined, clientIp);
  } catch (error: unknown) {
    if (error instanceof WebAuthError) {
      const status =
        error.code === "rate_limited"
          ? 429
          : error.code === "password_already_set" || error.code === "email_taken"
            ? 409
            : 400;
      return NextResponse.json({ error: error.code }, { status });
    }
    return NextResponse.json({ error: "recover_failed" }, { status: 502 });
  }

  const session = createUserSession(telegramId);
  if (!session) return NextResponse.json({ error: "auth_not_configured" }, { status: 503 });

  const response = NextResponse.json({ ok: true });
  response.cookies.set(USER_SESSION_COOKIE, session, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: USER_SESSION_TTL_SECONDS,
  });
  return response;
}

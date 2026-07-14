import { NextResponse } from "next/server";

import { WebAuthError, loginWebAccount } from "@/lib/billing/client";
import { USER_SESSION_COOKIE, USER_SESSION_TTL_SECONDS, createUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Log in with email + password → session cookie. */
export async function POST(request: Request) {
  let body: { email?: unknown; password?: unknown };
  try {
    body = (await request.json()) as { email?: unknown; password?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!EMAIL_RE.test(email) || !password) {
    return NextResponse.json({ error: "invalid_credentials" }, { status: 401 });
  }

  let telegramId: number;
  try {
    telegramId = await loginWebAccount(email, password);
  } catch (error: unknown) {
    if (error instanceof WebAuthError) {
      if (error.code === "rate_limited") return NextResponse.json({ error: "rate_limited" }, { status: 429 });
      return NextResponse.json({ error: "invalid_credentials" }, { status: 401 });
    }
    return NextResponse.json({ error: "login_failed" }, { status: 502 });
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

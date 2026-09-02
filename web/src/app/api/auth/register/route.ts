import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { WebAuthError, registerWebAccount } from "@/lib/billing/client";
import { SOURCE_COOKIE } from "@/lib/site";
import { USER_SESSION_COOKIE, USER_SESSION_TTL_SECONDS, createUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MIN_PASSWORD = 8;

/** Register a site account (email + password) → session cookie. */
export async function POST(request: Request) {
  let body: { email?: unknown; password?: unknown };
  try {
    body = (await request.json()) as { email?: unknown; password?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!EMAIL_RE.test(email) || email.length > 320) {
    return NextResponse.json({ error: "invalid_email" }, { status: 400 });
  }
  if (password.length < MIN_PASSWORD || password.length > 200) {
    return NextResponse.json({ error: "weak_password" }, { status: 400 });
  }

  let telegramId: number;
  try {
    telegramId = await registerWebAccount(email, password, cookies().get(SOURCE_COOKIE)?.value);
  } catch (error: unknown) {
    if (error instanceof WebAuthError) {
      if (error.code === "rate_limited") return NextResponse.json({ error: "rate_limited" }, { status: 429 });
      if (error.code === "already_registered")
        return NextResponse.json({ error: "already_registered" }, { status: 409 });
      return NextResponse.json({ error: error.code }, { status: 400 });
    }
    return NextResponse.json({ error: "register_failed" }, { status: 502 });
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

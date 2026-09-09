import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { attachTelegramToWebAccount } from "@/lib/billing/client";
import { verifyTelegramLoginWidget } from "@/lib/telegram-auth";
import {
  USER_SESSION_COOKIE,
  USER_SESSION_TTL_SECONDS,
  createUserSession,
  verifyUserSession,
} from "@/lib/web-session";

export const dynamic = "force-dynamic";

/** Log in with a Telegram Login Widget payload → httpOnly session cookie. */
export async function POST(request: Request) {
  let payload: Record<string, unknown>;
  try {
    payload = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const telegramId = verifyTelegramLoginWidget(payload);
  if (!telegramId) {
    return NextResponse.json({ error: "invalid_signature" }, { status: 401 });
  }

  // Signed into a website account already? Then this person is holding both
  // proofs at once — the cabinet session and a verified Telegram login — and
  // that is what lets the two accounts become one. Without this the login
  // merely swapped the session and the purchase stayed behind, which is how a
  // buyer ended up staring at an empty cabinet.
  const current = verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value);
  const username = typeof payload.username === "string" ? payload.username : undefined;
  const finalId =
    current !== null && current < 0
      ? await attachTelegramToWebAccount(current, telegramId, username)
      : telegramId;

  const session = createUserSession(finalId);
  if (!session) {
    return NextResponse.json({ error: "auth_not_configured" }, { status: 503 });
  }

  const response = NextResponse.json({ ok: true, telegramId: finalId });
  response.cookies.set(USER_SESSION_COOKIE, session, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: USER_SESSION_TTL_SECONDS,
  });
  return response;
}

/** Who am I — session state for client components. */
export async function GET() {
  const telegramId = verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value);
  if (!telegramId) {
    return NextResponse.json({ authenticated: false }, { status: 401 });
  }
  return NextResponse.json({ authenticated: true, telegramId });
}

/** Logout. */
export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(USER_SESSION_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}

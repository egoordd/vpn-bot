import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { updateAccountEmail } from "@/lib/billing/client";
import { USER_SESSION_COOKIE, verifyUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Change the receipt email for the logged-in (session cookie) account. */
export async function POST(request: Request) {
  const telegramId = verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value);
  if (!telegramId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let body: { email?: unknown };
  try {
    body = (await request.json()) as { email?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (!EMAIL_RE.test(email) || email.length > 320) {
    return NextResponse.json({ error: "invalid_email" }, { status: 400 });
  }

  const ok = await updateAccountEmail(telegramId, email);
  if (!ok) {
    return NextResponse.json({ error: "update_failed" }, { status: 502 });
  }
  return NextResponse.json({ ok: true, email });
}

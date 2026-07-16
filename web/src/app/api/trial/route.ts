import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { activateWebTrial } from "@/lib/billing/client";
import { USER_SESSION_COOKIE, verifyUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

/**
 * Site-side trial activation. Identity comes ONLY from the signed session
 * cookie (Telegram login or email account) — never from the request body.
 */
export async function POST() {
  const telegramId = verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value);
  if (!telegramId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const result = await activateWebTrial(telegramId);
  if (result.ok) {
    return NextResponse.json({ ok: true, subscriptionUrl: result.subscriptionUrl });
  }
  const status = result.error === "unavailable" ? 502 : 409;
  return NextResponse.json({ error: result.error }, { status });
}

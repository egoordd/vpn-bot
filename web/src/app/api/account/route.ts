import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { getAccountByTelegram } from "@/lib/billing/client";
import { verifyTelegramInitData } from "@/lib/telegram-auth";
import { USER_SESSION_COOKIE, verifyUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

/**
 * Account overview for the cabinet.
 *
 * SECURITY: identity comes ONLY from server-verified credentials — the site's
 * signed session cookie (set after a verified Telegram Login Widget payload)
 * or a signed Telegram Mini App `initData`. A client-supplied user id is never
 * trusted (IDOR).
 */
export async function GET(request: Request) {
  const initData =
    request.headers.get("x-telegram-init-data") ??
    new URL(request.url).searchParams.get("initData") ??
    "";

  const telegramId =
    verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value) ??
    verifyTelegramInitData(initData);
  if (!telegramId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const account = await getAccountByTelegram(telegramId);
  if (!account) {
    return NextResponse.json({ error: "account_not_found" }, { status: 404 });
  }

  return NextResponse.json(account);
}

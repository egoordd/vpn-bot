import { NextResponse } from "next/server";

import { verifyTelegramInitData } from "@/lib/telegram-auth";

export const dynamic = "force-dynamic";

/**
 * Account overview for the cabinet.
 *
 * SECURITY: identity MUST come from a signed Telegram Mini App `initData`
 * (validated server-side), never from a client-supplied user id — trusting a
 * client id here is an IDOR that would leak every user's subscription link and
 * balance. The endpoint refuses any request without a valid signature.
 *
 * The billing lookup keys on the internal account id; binding the authenticated
 * Telegram id to that account is not wired yet, so authenticated calls return
 * 501 until the cabinet mini-app + identity binding lands. This guarantees no
 * account data can ever be read for an attacker-chosen id.
 */
export async function GET(request: Request) {
  const initData =
    request.headers.get("x-telegram-init-data") ??
    new URL(request.url).searchParams.get("initData") ??
    "";

  const telegramId = verifyTelegramInitData(initData);
  if (!telegramId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  return NextResponse.json(
    { error: "account lookup not enabled yet" },
    { status: 501 },
  );
}

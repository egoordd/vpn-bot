import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { signOutEverywhere } from "@/lib/billing/client";
import { USER_SESSION_COOKIE, verifyUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

/** «Выйти на всех устройствах»: гаснут все сессии аккаунта, включая эту. */
export async function POST() {
  const telegramId = await verifyUserSession((await cookies()).get(USER_SESSION_COOKIE)?.value);
  if (!telegramId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let ok = false;
  try {
    ok = await signOutEverywhere(telegramId);
  } catch {
    ok = false;
  }
  if (!ok) return NextResponse.json({ error: "sign_out_failed" }, { status: 502 });

  const response = NextResponse.json({ ok: true });
  response.cookies.set(USER_SESSION_COOKIE, "", { httpOnly: true, secure: true, path: "/", maxAge: 0 });
  return response;
}

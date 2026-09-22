import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { WebAuthError, changeWebPassword } from "@/lib/billing/client";
import { clientIpFrom } from "@/lib/client-ip";
import { USER_SESSION_COOKIE, signedInResponse, verifyUserSession } from "@/lib/web-session";

export const dynamic = "force-dynamic";

/** Смена пароля в кабинете. Аккаунт — из подписанной сессии, не из запроса. */
export async function POST(request: Request) {
  const telegramId = await verifyUserSession((await cookies()).get(USER_SESSION_COOKIE)?.value);
  if (!telegramId) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: { currentPassword?: unknown; newPassword?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const currentPassword = typeof body.currentPassword === "string" ? body.currentPassword : "";
  const newPassword = typeof body.newPassword === "string" ? body.newPassword : "";
  if (!currentPassword) return NextResponse.json({ error: "invalid_credentials" }, { status: 403 });
  if (newPassword.length < 8 || newPassword.length > 200) {
    return NextResponse.json({ error: "weak_password" }, { status: 400 });
  }

  try {
    await changeWebPassword(telegramId, currentPassword, newPassword, clientIpFrom(request));
  } catch (error: unknown) {
    if (error instanceof WebAuthError) {
      const status = error.code === "rate_limited" ? 429 : error.code === "invalid_credentials" ? 403 : 400;
      return NextResponse.json({ error: error.code }, { status });
    }
    return NextResponse.json({ error: "password_failed" }, { status: 502 });
  }
  // Новый пароль гасит все сессии аккаунта, эту — тоже; выдаём ей новую.
  return signedInResponse(telegramId);
}

import { NextResponse } from "next/server";

import { WebAuthError, resetWebPassword } from "@/lib/billing/client";
import { clientIpFrom } from "@/lib/client-ip";
import { signedInResponse } from "@/lib/web-session";

export const dynamic = "force-dynamic";

/** Новый пароль по одноразовой ссылке из письма — и сразу вход в кабинет. */
export async function POST(request: Request) {
  let body: { token?: unknown; password?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const token = typeof body.token === "string" ? body.token.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (token.length < 16 || token.length > 128) {
    return NextResponse.json({ error: "invalid_token" }, { status: 400 });
  }
  if (password.length < 8 || password.length > 200) {
    return NextResponse.json({ error: "weak_password" }, { status: 400 });
  }

  try {
    const telegramId = await resetWebPassword(token, password, clientIpFrom(request));
    return signedInResponse(telegramId);
  } catch (error: unknown) {
    if (error instanceof WebAuthError) {
      return NextResponse.json({ error: error.code }, { status: error.code === "rate_limited" ? 429 : 400 });
    }
    return NextResponse.json({ error: "reset_failed" }, { status: 502 });
  }
}

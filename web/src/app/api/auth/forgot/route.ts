import { NextResponse } from "next/server";

import { WebAuthError, requestPasswordReset } from "@/lib/billing/client";
import { clientIpFrom } from "@/lib/client-ip";

export const dynamic = "force-dynamic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/**
 * «Забыли пароль?»: письмо со ссылкой на новый пароль. Ответ один и тот же,
 * есть такой аккаунт или нет, — страница не подсказывает, чья почта у нас.
 */
export async function POST(request: Request) {
  let body: { email?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  if (!EMAIL_RE.test(email) || email.length > 320) {
    return NextResponse.json({ error: "invalid_email" }, { status: 400 });
  }

  try {
    await requestPasswordReset(email, clientIpFrom(request));
  } catch (error: unknown) {
    if (error instanceof WebAuthError) {
      const status = error.code === "rate_limited" ? 429 : error.code === "mail_unavailable" ? 503 : 400;
      return NextResponse.json({ error: error.code }, { status });
    }
    return NextResponse.json({ error: "forgot_failed" }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}

import { NextResponse } from "next/server";

import { WebAuthError, setOrderPassword } from "@/lib/billing/client";
import { clientIpFrom } from "@/lib/client-ip";
import { signedInResponse } from "@/lib/web-session";

export const dynamic = "force-dynamic";

const ORDER_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

/**
 * Свой пароль вместо временного из письма — прямо со страницы оплаты, и сразу
 * вход в кабинет. Номер заказа знает только браузер покупателя; биллинг
 * разрешает это лишь аккаунту, созданному этим заказом, и только пока пароль
 * ещё временный.
 */
export async function POST(request: Request, { params }: { params: { orderId: string } }) {
  const orderId = params.orderId ?? "";
  if (!ORDER_ID_RE.test(orderId)) {
    return NextResponse.json({ error: "order_not_found" }, { status: 404 });
  }
  let body: { password?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const password = typeof body.password === "string" ? body.password : "";
  if (password.length < 8 || password.length > 200) {
    return NextResponse.json({ error: "weak_password" }, { status: 400 });
  }

  try {
    const telegramId = await setOrderPassword(orderId, password, clientIpFrom(request));
    return signedInResponse(telegramId);
  } catch (error: unknown) {
    if (error instanceof WebAuthError) {
      const status = error.code === "rate_limited" ? 429
        : error.code === "password_change_not_allowed" ? 409 : 400;
      return NextResponse.json({ error: error.code }, { status });
    }
    return NextResponse.json({ error: "password_failed" }, { status: 502 });
  }
}

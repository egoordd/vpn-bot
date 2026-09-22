import crypto from "node:crypto";

import { NextResponse } from "next/server";

import { TELEGRAM_LOGIN_COOKIE, TELEGRAM_LOGIN_TTL_SECONDS, telegramLoginUrl } from "@/lib/telegram-auth";

export const dynamic = "force-dynamic";

/**
 * Начало входа через Telegram: ставим одноразовую отметку и отправляем в Telegram.
 *
 * Вход и привязка к аккаунту сайта принимаются, только если отметка есть в
 * браузере. Иначе подготовленная ссылка с чужим подписанным входом Telegram
 * привязывала подписку жертвы к Telegram атакующего (аудит 22.09.2026, SEC-01).
 */
export async function GET(request: Request) {
  // Адрес возврата — от домена, на котором человек сейчас: Telegram сверяет origin.
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? "unlockproject.site";
  const proto = request.headers.get("x-forwarded-proto") ?? "https";
  const href = telegramLoginUrl(`${proto}://${host}/auth/telegram/callback`);
  if (!href) return NextResponse.redirect(new URL("/cabinet", `${proto}://${host}`));

  const response = NextResponse.redirect(href);
  response.cookies.set(TELEGRAM_LOGIN_COOKIE, crypto.randomBytes(16).toString("hex"), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: TELEGRAM_LOGIN_TTL_SECONDS,
  });
  return response;
}

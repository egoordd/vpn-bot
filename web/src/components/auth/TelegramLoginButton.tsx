"use client";

import { useEffect, useRef } from "react";

declare global {
  interface Window {
    onTelegramAuth?: (user: Record<string, unknown>) => void;
  }
}

interface TelegramLoginButtonProps {
  onSuccess?: () => void;
  onError?: (message: string) => void;
}

/**
 * Official Telegram Login Widget. Renders an iframe button; Telegram calls
 * `onTelegramAuth` with a signed payload which we verify server-side before
 * setting the session cookie.
 *
 * NOTE: the widget only works on the domain registered via @BotFather
 * /setdomain for the bot.
 */
export function TelegramLoginButton({ onSuccess, onError }: TelegramLoginButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    window.onTelegramAuth = async (user: Record<string, unknown>) => {
      try {
        const res = await fetch("/api/auth/telegram", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(user),
        });
        if (!res.ok) {
          onError?.("Не удалось войти через Telegram. Попробуйте ещё раз.");
          return;
        }
        onSuccess?.();
      } catch {
        onError?.("Сеть недоступна. Попробуйте ещё раз.");
      }
    };

    const botName = process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "unlkvpn_bot";
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botName);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "12");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    container.appendChild(script);

    return () => {
      container.innerHTML = "";
      delete window.onTelegramAuth;
    };
  }, [onSuccess, onError]);

  return <div ref={containerRef} />;
}

"use client";

import { useCallback, useState } from "react";

import { TelegramLoginButton } from "@/components/auth/TelegramLoginButton";

export function CabinetLogin({ note }: { note?: string }) {
  const [error, setError] = useState<string | null>(null);

  const onSuccess = useCallback(() => {
    window.location.reload();
  }, []);

  return (
    <div className="card cab__login">
      <h2>Вход в кабинет</h2>
      <p className="cab__login-lead">
        Войдите через Telegram — подписка, ссылка для подключения и баланс появятся здесь.
      </p>
      {note && <p className="cab__login-note">{note}</p>}
      <TelegramLoginButton onSuccess={onSuccess} onError={setError} />
      {error && <p className="cab__login-error">{error}</p>}
      <p className="cab__login-alt mono">
        Покупали по email? Ссылка-подписка была показана после оплаты; вход по email появится
        позже. Вопросы — @unlock_support_bot.
      </p>
    </div>
  );
}

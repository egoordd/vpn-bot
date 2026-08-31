"use client";

import { useState } from "react";

import { TelegramLoginButton } from "@/components/auth/TelegramLoginButton";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type Mode = "login" | "register";

const ERRORS: Record<string, string> = {
  invalid_email: "Проверьте email — он выглядит некорректно.",
  weak_password: "Пароль должен быть не короче 8 символов.",
  already_registered: "Аккаунт с этим email уже есть. Войдите вместо регистрации.",
  invalid_credentials: "Неверный email или пароль.",
  rate_limited: "Слишком много попыток. Подождите несколько минут.",
};

interface CabinetLoginProps {
  /** Where "Войти через Telegram" points; null when the bot token is unset. */
  telegramLoginHref: string | null;
  note?: string;
}

export function CabinetLogin({ telegramLoginHref, note }: CabinetLoginProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (!EMAIL_RE.test(email.trim())) {
      setError(ERRORS.invalid_email);
      return;
    }
    if (mode === "register" && password.length < 8) {
      setError(ERRORS.weak_password);
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`/api/auth/${mode === "register" ? "register" : "login"}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(ERRORS[body.error ?? ""] ?? "Не удалось. Попробуйте ещё раз.");
        setBusy(false);
        return;
      }
      window.location.reload();
    } catch {
      setError("Сеть недоступна. Попробуйте ещё раз.");
      setBusy(false);
    }
  }

  return (
    <div className="card cab__login">
      <h2>Вход в кабинет</h2>
      <p className="cab__login-lead">
        Здесь ваши подписки, ссылка для подключения и баланс.
      </p>
      {note && <p className="cab__login-note">{note}</p>}

      <div className="cab__login-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={mode === "login"}
          className={`cab__login-tab${mode === "login" ? " is-active" : ""}`}
          onClick={() => {
            setMode("login");
            setError(null);
          }}
        >
          Вход
        </button>
        <button
          role="tab"
          aria-selected={mode === "register"}
          className={`cab__login-tab${mode === "register" ? " is-active" : ""}`}
          onClick={() => {
            setMode("register");
            setError(null);
          }}
        >
          Регистрация
        </button>
      </div>

      <div className="cab__login-form">
        <input
          className="cab__login-input"
          type="email"
          inputMode="email"
          autoComplete="email"
          placeholder="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
        />
        <input
          className="cab__login-input"
          type="password"
          autoComplete={mode === "register" ? "new-password" : "current-password"}
          placeholder={mode === "register" ? "придумайте пароль (8+ символов)" : "пароль"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        {error && <p className="cab__login-error">{error}</p>}
        <button className="cab__login-submit" onClick={submit} disabled={busy}>
          {busy ? "Секунду…" : mode === "register" ? "Создать аккаунт" : "Войти"}
        </button>
      </div>

      <div className="cab__login-or mono">или</div>
      <TelegramLoginButton href={telegramLoginHref} />

      <p className="cab__login-alt mono">
        Покупали по email? Зарегистрируйтесь с тем же адресом — прошлые покупки появятся
        автоматически. Вопросы — @unlock_support_bot.
      </p>
    </div>
  );
}

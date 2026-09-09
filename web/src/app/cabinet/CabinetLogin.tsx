"use client";

import { useState } from "react";

import { TelegramLoginButton } from "@/components/auth/TelegramLoginButton";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type Mode = "login" | "register" | "recover";

const ERRORS: Record<string, string> = {
  invalid_email: "Проверьте email — он выглядит некорректно.",
  weak_password: "Пароль должен быть не короче 8 символов.",
  already_registered: "Для этого email уже есть аккаунт. Войдите с паролем, а если покупали без регистрации — задайте пароль по ссылке подписки на вкладке «По ссылке».",
  invalid_subscription: "Ссылка не подошла. Скопируйте её целиком из приложения или из письма о выдаче.",
  password_already_set: "У этого аккаунта уже есть пароль. Войдите с ним, а если забыли — напишите в поддержку.",
  email_taken: "Этот email занят другим аккаунтом. Оставьте поле пустым или укажите другой.",
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
  const [subscription, setSubscription] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    // Recovery identifies the account by the link, so an address there is
    // optional — a guest who never gave one can still set a password.
    if (mode !== "recover" && !EMAIL_RE.test(email.trim())) {
      setError(ERRORS.invalid_email);
      return;
    }
    if (mode === "recover" && email.trim() && !EMAIL_RE.test(email.trim())) {
      setError(ERRORS.invalid_email);
      return;
    }
    if (mode === "recover" && !subscription.trim()) {
      setError(ERRORS.invalid_subscription);
      return;
    }
    if (mode !== "login" && password.length < 8) {
      setError(ERRORS.weak_password);
      return;
    }
    setBusy(true);
    try {
      const endpoint =
        mode === "register" ? "register" : mode === "recover" ? "recover" : "login";
      const payload =
        mode === "recover"
          ? {
              subscription: subscription.trim(),
              password,
              ...(email.trim() ? { email: email.trim().toLowerCase() } : {}),
            }
          : { email: email.trim().toLowerCase(), password };
      const res = await fetch(`/api/auth/${endpoint}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
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
        Здесь ваши подписки и ссылка для подключения.
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
        <button
          role="tab"
          aria-selected={mode === "recover"}
          className={`cab__login-tab${mode === "recover" ? " is-active" : ""}`}
          onClick={() => {
            setMode("recover");
            setError(null);
          }}
        >
          По ссылке
        </button>
      </div>

      <div className="cab__login-form">
        {mode === "recover" && (
          <>
            <p className="cab__login-note">
              Покупали без пароля или потеряли доступ? Вставьте ссылку своей подписки —
              она есть в приложении и в письме о выдаче — и задайте пароль. Дальше будете
              входить как обычно.
            </p>
            <input
              className="cab__login-input"
              type="url"
              inputMode="url"
              autoComplete="off"
              placeholder="https://sub.unlockvpn.site/sub/…"
              value={subscription}
              onChange={(e) => setSubscription(e.target.value)}
              disabled={busy}
            />
          </>
        )}
        <input
          className="cab__login-input"
          type="email"
          inputMode="email"
          autoComplete="email"
          placeholder={mode === "recover" ? "email (необязательно)" : "email"}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
        />
        <input
          className="cab__login-input"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder={mode === "login" ? "пароль" : "придумайте пароль (8+ символов)"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        {error && <p className="cab__login-error">{error}</p>}
        <button className="cab__login-submit" onClick={submit} disabled={busy}>
          {busy
            ? "Секунду…"
            : mode === "register"
              ? "Создать аккаунт"
              : mode === "recover"
                ? "Задать пароль и войти"
                : "Войти"}
        </button>
      </div>

      <div className="cab__login-or mono">или</div>
      <TelegramLoginButton href={telegramLoginHref} />

      <p className="cab__login-alt mono">
        Покупали по email без пароля? Откройте вкладку «По ссылке» — задайте пароль,
        подтвердив владение ссылкой подписки. Если ссылки под рукой нет, напишите в{" "}
        <a href="https://t.me/unlock_support_bot">@unlock_support_bot</a>.
      </p>
    </div>
  );
}

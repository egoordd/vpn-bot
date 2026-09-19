"use client";

import { useEffect, useState } from "react";

const ERRORS: Record<string, string> = {
  invalid_token: "Ссылка устарела или уже использована. Запросите новую: «Забыли пароль?» на странице входа.",
  weak_password: "Пароль должен быть не короче 8 символов.",
  rate_limited: "Слишком много попыток. Подождите несколько минут.",
};

export function ResetClient() {
  // Токен лежит во фрагменте (#t=…): так он не уходит на сервер и не попадает в журналы.
  const [token, setToken] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get("t");
    setToken(value && value.length >= 16 ? value : "");
  }, []);

  async function submit() {
    if (password.length < 8) {
      setError(ERRORS.weak_password);
      return;
    }
    if (password !== repeat) {
      setError("Пароли не совпадают.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const res = await fetch("/api/auth/reset", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(ERRORS[body.error ?? ""] ?? "Не удалось сохранить. Попробуйте ещё раз.");
        setBusy(false);
        return;
      }
      window.location.href = "/cabinet";
    } catch {
      setError("Сеть недоступна. Попробуйте ещё раз.");
      setBusy(false);
    }
  }

  if (token === null) return null;

  return (
    <div className="card cab__login">
      <h2>Новый пароль</h2>
      {token === "" ? (
        <p className="cab__login-error">
          В ссылке нет кода. Откройте её из письма целиком или запросите новую: «Забыли пароль?» на{" "}
          <a href="/cabinet">странице входа</a>.
        </p>
      ) : (
        <div className="cab__login-form">
          <p className="cab__login-note">Не короче 8 символов.</p>
          <input
            className="cab__login-input"
            type="password"
            autoComplete="new-password"
            placeholder="новый пароль"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
          <input
            className="cab__login-input"
            type="password"
            autoComplete="new-password"
            placeholder="повторите пароль"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void submit()}
            disabled={busy}
          />
          {error && <p className="cab__login-error">{error}</p>}
          <button className="cab__login-submit" onClick={() => void submit()} disabled={busy}>
            {busy ? "Сохраняем…" : "Сохранить и войти"}
          </button>
        </div>
      )}
    </div>
  );
}

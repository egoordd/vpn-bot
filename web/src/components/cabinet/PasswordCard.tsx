"use client";

import { useState } from "react";

const ERRORS: Record<string, string> = {
  invalid_credentials: "Текущий пароль не подошёл. Не помните его — выйдите и нажмите «Забыли пароль?».",
  weak_password: "Новый пароль должен быть не короче 8 символов.",
  rate_limited: "Слишком много попыток. Подождите несколько минут.",
};

/** Смена пароля аккаунта сайта — например, временного из письма после оплаты. */
export function PasswordCard() {
  const [editing, setEditing] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function close() {
    setEditing(false);
    setCurrent("");
    setNext("");
    setError(null);
  }

  async function save() {
    if (next.length < 8) {
      setError(ERRORS.weak_password);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/password", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ currentPassword: current, newPassword: next }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(ERRORS[body.error ?? ""] ?? "Не удалось сохранить. Попробуйте ещё раз.");
        return;
      }
      close();
      setSaved(true);
    } catch {
      setError("Сеть недоступна. Попробуйте ещё раз.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="card email-card">
      <div className="card__head">
        <span className="card__title">Пароль</span>
      </div>

      {editing ? (
        <div className="email-card__form">
          <input
            className="email-card__input"
            type="password"
            autoComplete="current-password"
            placeholder="текущий пароль"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            disabled={saving}
          />
          <input
            className="email-card__input"
            type="password"
            autoComplete="new-password"
            placeholder="новый пароль (8+ символов)"
            value={next}
            onChange={(event) => setNext(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void save()}
            disabled={saving}
          />
          {error && <p className="email-card__error">{error}</p>}
          <div className="email-card__actions">
            <button
              type="button"
              className="email-card__btn email-card__btn--primary"
              onClick={() => void save()}
              disabled={saving}
            >
              {saving ? "Сохраняем…" : "Сохранить"}
            </button>
            <button type="button" className="email-card__btn" onClick={close} disabled={saving}>
              Отмена
            </button>
          </div>
        </div>
      ) : (
        <div className="email-card__view">
          <p className="email-card__value mono">{saved ? "✅ пароль изменён" : "••••••••"}</p>
          <button
            type="button"
            className="email-card__btn"
            onClick={() => {
              setSaved(false);
              setEditing(true);
            }}
          >
            Сменить
          </button>
        </div>
      )}

      <p className="email-card__note mono">
        Вошли по временному паролю из письма? Замените его на свой.
      </p>
    </article>
  );
}

"use client";

import { useState } from "react";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Receipt email: shown and editable right in the cabinet (54-ФЗ чеки). */
export function EmailCard({ email }: { email: string | null }) {
  const [current, setCurrent] = useState(email);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(email ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const next = value.trim().toLowerCase();
    if (!EMAIL_RE.test(next)) {
      setError("Проверьте адрес — он выглядит некорректно.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/account/email", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: next }),
      });
      if (!res.ok) {
        setError("Не удалось сохранить. Попробуйте ещё раз.");
        return;
      }
      setCurrent(next);
      setEditing(false);
    } catch {
      setError("Сеть недоступна. Попробуйте ещё раз.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="card email-card">
      <div className="card__head">
        <span className="card__title">Email для чеков</span>
      </div>

      {editing ? (
        <div className="email-card__form">
          <input
            className="email-card__input"
            type="email"
            inputMode="email"
            autoComplete="email"
            placeholder="name@mail.ru"
            value={value}
            onChange={(event) => setValue(event.target.value)}
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
            <button
              type="button"
              className="email-card__btn"
              onClick={() => {
                setEditing(false);
                setValue(current ?? "");
                setError(null);
              }}
              disabled={saving}
            >
              Отмена
            </button>
          </div>
        </div>
      ) : (
        <div className="email-card__view">
          <p className="email-card__value mono">{current ?? "не указан"}</p>
          <button type="button" className="email-card__btn" onClick={() => setEditing(true)}>
            {current ? "Изменить" : "Указать"}
          </button>
        </div>
      )}

      <p className="email-card__note mono">
        Сюда приходят чеки об оплате картой. Изменить можно и в боте: /email.
      </p>
    </article>
  );
}

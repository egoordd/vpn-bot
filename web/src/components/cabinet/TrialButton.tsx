"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";

/**
 * One-tap trial activation for a logged-in cabinet user: hits /api/trial and
 * reloads the cabinet on success so the subscription + connect cards appear —
 * the same «paid → delivered» feel the bot gives.
 */
export function TrialButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function activate() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/trial", { method: "POST" });
      if (res.ok) {
        window.location.reload();
        return;
      }
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (body.error === "trial_already_used") {
        setError("Пробный период уже был использован. Выберите тариф — ссылка останется той же.");
      } else if (body.error === "has_active_subscription") {
        window.location.reload();
        return;
      } else if (res.status === 401) {
        setError("Сессия истекла — войдите заново.");
      } else {
        setError("Не получилось активировать. Попробуйте через минуту или напишите в поддержку.");
      }
    } catch {
      setError("Сеть недоступна. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="trialbtn">
      <Button className="sub__cta" onClick={activate} disabled={busy}>
        {busy ? "Активируем…" : "Активировать пробный период — 3 дня"}
      </Button>
      {error && <p className="trialbtn__error">{error}</p>}
    </div>
  );
}

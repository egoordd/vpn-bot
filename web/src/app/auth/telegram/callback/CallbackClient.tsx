"use client";

import { useEffect, useState } from "react";

type State = "working" | "failed";

/** Telegram returns the signed payload base64'd in `#tgAuthResult=…`. */
function readAuthResult(hash: string): Record<string, unknown> | null {
  const match = /tgAuthResult=([^&]+)/.exec(hash);
  if (!match) return null;
  try {
    const normalised = match[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalised + "=".repeat((4 - (normalised.length % 4)) % 4);
    const parsed: unknown = JSON.parse(atob(padded));
    return typeof parsed === "object" && parsed !== null
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export function CallbackClient() {
  const [state, setState] = useState<State>("working");

  useEffect(() => {
    const payload = readAuthResult(window.location.hash);
    if (!payload) {
      setState("failed");
      return;
    }
    // The signature is checked server-side against the bot token; nothing here
    // is trusted, the payload is only carried across.
    void (async () => {
      try {
        const res = await fetch("/api/auth/telegram", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          setState("failed");
          return;
        }
        window.location.replace("/cabinet");
      } catch {
        setState("failed");
      }
    })();
  }, []);

  if (state === "failed") {
    return (
      <div className="card cab__login">
        <h2>Не удалось войти</h2>
        <p className="cab__login-alt mono">
          Telegram не подтвердил вход. Попробуйте ещё раз или войдите по email.
        </p>
        <a className="cab__login-submit" href="/cabinet">
          Вернуться в кабинет
        </a>
      </div>
    );
  }

  return (
    <div className="card cab__login">
      <h2>Входим…</h2>
      <p className="cab__login-alt mono">Секунду, проверяем подпись Telegram.</p>
    </div>
  );
}

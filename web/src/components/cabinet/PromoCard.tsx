"use client";

import { useState } from "react";

import type { PromoFailure, PromoRedemption } from "@/lib/billing/types";
import "./promo-card.css";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; result: PromoRedemption }
  | { status: "error"; message: string };

/** One sentence per reason. The card used to answer "не найден" to everything,
 *  including codes that were merely spent or already used by this account. */
const FAILURES: Record<PromoFailure, string> = {
  promo_not_found: "Такого промокода нет. Проверьте раскладку и лишние пробелы.",
  promo_expired: "Срок действия промокода истёк.",
  promo_inactive: "Промокод отключён.",
  promo_exhausted: "Промокод уже разобрали — закончились активации.",
  promo_user_limit: "Вы уже использовали этот промокод.",
  promo_min_amount: "Промокод действует от большей суммы.",
  promo_wrong_type: "Этот промокод применяется при оплате, а не здесь.",
  unauthorized: "Войдите в кабинет, чтобы применить промокод.",
  unavailable: "Не удалось проверить промокод. Попробуйте позже.",
};

export function PromoCard() {
  const [code, setCode] = useState("");
  const [state, setState] = useState<State>({ status: "idle" });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = code.trim();
    if (!trimmed) return;
    setState({ status: "loading" });
    try {
      const res = await fetch("/api/promo", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ code: trimmed }),
      });
      const data = (await res.json()) as { result?: PromoRedemption; error?: PromoFailure };
      if (!res.ok || !data.result) {
        setState({ status: "error", message: FAILURES[data.error ?? "unavailable"] ?? FAILURES.unavailable });
        return;
      }
      setCode("");
      setState({ status: "ok", result: data.result });
    } catch {
      setState({ status: "error", message: FAILURES.unavailable });
    }
  }

  return (
    <article className="card promo">
      <div className="card__head">
        <span className="card__title">Промокод</span>
      </div>

      <form className="promo__form" onSubmit={onSubmit}>
        <input
          className="promo__input mono"
          type="text"
          inputMode="text"
          autoCapitalize="characters"
          placeholder="WELCOME"
          aria-label="Введите промокод"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
        <button type="submit" className="promo__btn" disabled={state.status === "loading"}>
          {state.status === "loading" ? "Применяю…" : "Применить"}
        </button>
      </form>

      <div className="promo__result" aria-live="polite">
        {state.status === "ok" && (
          <p className="promo__ok">
            Промокод применён: подписка на <strong>{state.result.grantedDays} дней</strong> уже
            активна. Ссылка для подключения — на этой странице.
          </p>
        )}
        {state.status === "error" && <p className="promo__err">{state.message}</p>}
        {state.status === "idle" && (
          <p className="promo__hint">Промокод откроет подписку сразу.</p>
        )}
      </div>
    </article>
  );
}

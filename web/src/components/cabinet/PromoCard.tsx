"use client";

import { useState } from "react";

import { formatRub } from "@/lib/money";
import type { DiscountResult } from "@/lib/billing/types";
import "./promo-card.css";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; result: DiscountResult }
  | { status: "error"; message: string };

/** Sample checkout amount used to preview a discount (Standard · 1 месяц). */
const SAMPLE_AMOUNT_KOPECKS = 14900;

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
        body: JSON.stringify({ code: trimmed, amountKopecks: SAMPLE_AMOUNT_KOPECKS }),
      });
      const data = (await res.json()) as { result: DiscountResult | null };
      if (!res.ok || !data.result) {
        setState({ status: "error", message: "Промокод не найден или недействителен." });
        return;
      }
      setState({ status: "ok", result: data.result });
    } catch {
      setState({ status: "error", message: "Не удалось проверить промокод. Попробуйте позже." });
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
          {state.status === "loading" ? "Проверяю…" : "Применить"}
        </button>
      </form>

      <div className="promo__result" aria-live="polite">
        {state.status === "ok" && (
          <p className="promo__ok">
            Скидка <strong>{formatRub(state.result.discountKopecks)}</strong> — к оплате{" "}
            <strong>{formatRub(state.result.finalKopecks)}</strong> вместо{" "}
            {formatRub(state.result.originalKopecks)}.
          </p>
        )}
        {state.status === "error" && <p className="promo__err">{state.message}</p>}
        {state.status === "idle" && (
          <p className="promo__hint">Скидка применится при следующей оплате тарифа.</p>
        )}
      </div>
    </article>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { TelegramLoginButton } from "@/components/auth/TelegramLoginButton";
import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { formatRubFromRubles } from "@/lib/money";

export const ORDER_STORAGE_KEY = "ulk_order";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const CHECKOUT_ERRORS: Record<string, string> = {
  payments_unavailable: "Оплата картой временно недоступна. Попробуйте позже или купите в Telegram-боте.",
  payment_create_failed: "Платёжная система не ответила. Попробуйте ещё раз через минуту.",
  invalid_email: "Проверьте email — он выглядит некорректно.",
  rate_limited: "Слишком много попыток оплаты. Подождите несколько минут и попробуйте снова.",
};

interface BuyClientProps {
  planCode: string;
  planTitle: string;
  priceRub: number;
  trafficGb: number | null;
  deviceLimit: number | null;
}

export function BuyClient({ planCode, planTitle, priceRub, trafficGb, deviceLimit }: BuyClientProps) {
  const [telegramId, setTelegramId] = useState<number | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshAuth = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/telegram", { cache: "no-store" });
      if (res.ok) {
        const body = (await res.json()) as { telegramId?: number };
        setTelegramId(typeof body.telegramId === "number" ? body.telegramId : null);
      } else {
        setTelegramId(null);
      }
    } catch {
      setTelegramId(null);
    } finally {
      setAuthChecked(true);
    }
  }, []);

  useEffect(() => {
    void refreshAuth();
  }, [refreshAuth]);

  const emailValid = EMAIL_RE.test(email.trim());
  const canSubmit = !submitting && (telegramId !== null || emailValid);

  async function submit() {
    setError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          plan: planCode,
          email: email.trim() || undefined,
        }),
      });
      const body = (await res.json()) as { orderId?: string; payUrl?: string; error?: string };
      if (!res.ok || !body.payUrl || !body.orderId) {
        setError(CHECKOUT_ERRORS[body.error ?? ""] ?? "Не удалось создать платёж. Попробуйте ещё раз.");
        setSubmitting(false);
        return;
      }
      try {
        window.localStorage.setItem(ORDER_STORAGE_KEY, body.orderId);
      } catch {
        // приватный режим — success-страница покажет запасную подсказку
      }
      window.location.href = body.payUrl;
    } catch {
      setError("Сеть недоступна. Проверьте соединение и попробуйте ещё раз.");
      setSubmitting(false);
    }
  }

  return (
    <div className="buy__card card">
      <header className="buy__head">
        <Pill tone="accent">Оплата картой</Pill>
        <h1 className="buy__title">{planTitle}</h1>
        <p className="buy__price">
          <span className="buy__price-value">{formatRubFromRubles(priceRub)}</span>
        </p>
        <ul className="buy__features mono">
          {trafficGb !== null && <li>{trafficGb} ГБ трафика</li>}
          {deviceLimit !== null && <li>до {deviceLimit} устройств</li>}
          <li>все локации и протоколы одной ссылкой</li>
        </ul>
      </header>

      <div className="buy__identity">
        {telegramId !== null ? (
          <p className="buy__tg-ok">
            ✅ Вы вошли через Telegram — ссылка-подписка придёт в бот и появится в{" "}
            <a href="/cabinet">кабинете</a>.
          </p>
        ) : (
          <>
            <label className="buy__label" htmlFor="buy-email">
              Email для доступа к конфигу и чека
            </label>
            <input
              id="buy-email"
              className="buy__input"
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder="name@mail.ru"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            {authChecked && (
              <div className="buy__tg-alt">
                <span className="buy__tg-alt-label mono">или войдите через Telegram:</span>
                <TelegramLoginButton onSuccess={refreshAuth} onError={setError} />
              </div>
            )}
          </>
        )}
      </div>

      {error && <p className="buy__error">{error}</p>}

      <Button size="lg" className="buy__submit" disabled={!canSubmit} onClick={submit}>
        {submitting ? "Создаём платёж…" : `Перейти к оплате · ${formatRubFromRubles(priceRub)}`}
      </Button>

      <p className="buy__note mono">
        Оплата проходит на защищённой странице ЮKassa. После оплаты вы вернётесь на сайт и получите
        ссылку-подписку.
      </p>
    </div>
  );
}

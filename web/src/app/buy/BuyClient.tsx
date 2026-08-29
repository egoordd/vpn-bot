"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { formatRubFromRubles } from "@/lib/money";
import { trafficLabel } from "@/lib/tariffs";

export const ORDER_STORAGE_KEY = "ulk_order";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const CHECKOUT_ERRORS: Record<string, string> = {
  payments_unavailable: "Оплата картой временно недоступна. Попробуйте позже или купите в Telegram-боте.",
  payment_create_failed: "Платёжная система не ответила. Попробуйте ещё раз через минуту.",
  invalid_email: "Проверьте email — он выглядит некорректно.",
  invalid_subscription: "Это не похоже на нашу ссылку-подписку. Скопируйте её целиком из приложения.",
  unknown_subscription: "По этой ссылке доступ не найден. Проверьте, что скопировали её целиком.",
  rate_limited: "Слишком много попыток оплаты. Подождите несколько минут и попробуйте снова.",
};

interface BuyClientProps {
  planCode: string;
  planTitle: string;
  priceRub: number;
  trafficGb: number | null;
  trafficResetsMonthly: boolean;
  deviceLimit: number | null;
}

export function BuyClient({
  planCode,
  planTitle,
  priceRub,
  trafficGb,
  trafficResetsMonthly,
  deviceLimit,
}: BuyClientProps) {
  const [telegramId, setTelegramId] = useState<number | null>(null);
  const [email, setEmail] = useState("");
  // A lapsed customer cannot open Telegram in Russia, so the link already in
  // their VPN app is how they point at the account to top up.
  const [renewing, setRenewing] = useState(false);
  const [subLink, setSubLink] = useState("");
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
    }
  }, []);

  useEffect(() => {
    void refreshAuth();
  }, [refreshAuth]);

  const emailValid = EMAIL_RE.test(email.trim());
  const subLinkFilled = subLink.trim().length > 12;
  const canSubmit =
    !submitting && (telegramId !== null || (renewing ? subLinkFilled : emailValid));

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
          subscription: renewing ? subLink.trim() || undefined : undefined,
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
        <Pill tone="accent">Оформление</Pill>
        <h1 className="buy__title">{planTitle}</h1>
        <p className="buy__price">
          <span className="buy__price-value">{formatRubFromRubles(priceRub)}</span>
        </p>
        <ul className="buy__features mono">
          {trafficLabel({ trafficGb, trafficResetsMonthly }) !== null && (
            <li>{trafficLabel({ trafficGb, trafficResetsMonthly })}</li>
          )}
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
        ) : renewing ? (
          <>
            <label className="buy__label" htmlFor="buy-sub">
              Ваша ссылка-подписка
            </label>
            <input
              id="buy-sub"
              className="buy__input mono"
              type="url"
              inputMode="url"
              autoComplete="off"
              placeholder="https://sub.unlockvpn.site/sub/…"
              value={subLink}
              onChange={(event) => setSubLink(event.target.value)}
            />
            <p className="buy__switch-note">
              Скопируйте её из приложения, где уже подключён VPN. Оплата продлит именно этот
              доступ, ссылка останется прежней.
            </p>
            <button type="button" className="buy__switch" onClick={() => setRenewing(false)}>
              Я здесь впервые, оформить новый доступ
            </button>
          </>
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
            <button type="button" className="buy__switch" onClick={() => setRenewing(true)}>
              У меня уже есть подписка, продлить её
            </button>
          </>
        )}
      </div>

      {error && <p className="buy__error">{error}</p>}

      <Button size="lg" className="buy__submit" disabled={!canSubmit} onClick={submit}>
        {submitting ? "Оформляем…" : `Купить · ${formatRubFromRubles(priceRub)}`}
      </Button>

      <p className="buy__note mono">
        Оплата проходит на защищённой странице. После оплаты вы вернётесь на сайт и получите
        ссылку-подписку.
      </p>
    </div>
  );
}

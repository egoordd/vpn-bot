"use client";

import { useEffect, useRef, useState } from "react";

import { CopyButton } from "@/components/ui/CopyButton";
import { Pill } from "@/components/ui/Pill";

const ORDER_STORAGE_KEY = "ulk_order";
const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

const APPS = [
  { name: "Happ", scheme: (url: string) => `happ://add/${encodeURIComponent(url)}` },
  { name: "V2RayTun", scheme: (url: string) => `v2raytun://import/${encodeURIComponent(url)}` },
  { name: "Hiddify", scheme: (url: string) => `hiddify://import/${encodeURIComponent(url)}` },
];

interface OrderSubscription {
  subscriptionUrl: string | null;
  planTitle: string | null;
  expiresAt: string | null;
  isActive: boolean;
}

type Phase = "loading" | "waiting" | "done" | "no-order" | "timeout";

export function SuccessClient() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [subscription, setSubscription] = useState<OrderSubscription | null>(null);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;

    let orderId: string | null = null;
    try {
      orderId =
        new URLSearchParams(window.location.search).get("order") ??
        window.localStorage.getItem(ORDER_STORAGE_KEY);
    } catch {
      orderId = null;
    }
    if (!orderId) {
      setPhase("no-order");
      return;
    }

    const startedAt = Date.now();

    async function poll(id: string) {
      if (stopped.current) return;
      try {
        const res = await fetch(`/api/order/${encodeURIComponent(id)}`, { cache: "no-store" });
        if (res.ok) {
          const body = (await res.json()) as {
            status: string;
            subscription?: OrderSubscription;
          };
          if (body.status === "succeeded" && body.subscription) {
            setSubscription(body.subscription);
            setPhase("done");
            try {
              window.localStorage.removeItem(ORDER_STORAGE_KEY);
            } catch {
              // ignore
            }
            return;
          }
        }
      } catch {
        // transient network error — keep polling
      }
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
        setPhase("timeout");
        return;
      }
      setPhase("waiting");
      window.setTimeout(() => void poll(id), POLL_INTERVAL_MS);
    }

    void poll(orderId);
    return () => {
      stopped.current = true;
    };
  }, []);

  if (phase === "loading" || phase === "waiting") {
    return (
      <div className="paysuccess__card card">
        <Pill tone="accent">Оплата</Pill>
        <h1>Ждём подтверждение оплаты…</h1>
        <p className="paysuccess__lead">
          Обычно это занимает меньше минуты. Страница обновится автоматически — не закрывайте её.
        </p>
        <div className="paysuccess__spinner" aria-hidden />
      </div>
    );
  }

  if (phase === "no-order") {
    return (
      <div className="paysuccess__card card">
        <Pill tone="warn">Заказ не найден</Pill>
        <h1>Не видим номер заказа</h1>
        <p className="paysuccess__lead">
          Если вы платили, войдя через Telegram — ссылка-подписка уже пришла в бот и доступна в{" "}
          <a href="/cabinet">кабинете</a>. Если платили по email и конфиг не получили — напишите в{" "}
          поддержку: @unlock_support_bot.
        </p>
      </div>
    );
  }

  if (phase === "timeout") {
    return (
      <div className="paysuccess__card card">
        <Pill tone="warn">Дольше обычного</Pill>
        <h1>Платёж ещё обрабатывается</h1>
        <p className="paysuccess__lead">
          Обновите страницу через пару минут. Если оплатили через Telegram — конфиг придёт в бот.
          Не пришёл за 15 минут — напишите в поддержку: @unlock_support_bot.
        </p>
      </div>
    );
  }

  const subUrl = subscription?.subscriptionUrl ?? null;

  return (
    <div className="paysuccess__card card">
      <Pill tone="accent">Готово</Pill>
      <h1>Оплата прошла — вот ваш доступ</h1>
      {subscription?.planTitle && (
        <p className="paysuccess__plan mono">{subscription.planTitle}</p>
      )}

      {subUrl ? (
        <>
          <p className="paysuccess__lead">
            Импортируйте ссылку-подписку в приложение — внутри все локации и протоколы, конфиг
            обновляется сам.
          </p>

          <div className="paysuccess__link">
            <code className="paysuccess__url mono">{subUrl}</code>
            <CopyButton value={subUrl} label="Скопировать ссылку" />
          </div>

          <div className="paysuccess__apps">
            <span className="paysuccess__apps-label mono">Открыть в:</span>
            {APPS.map((app) => (
              <a key={app.name} className="paysuccess__app" href={app.scheme(subUrl)}>
                {app.name}
              </a>
            ))}
          </div>

          <p className="paysuccess__note mono">
            Сохраните ссылку — она же доступна в <a href="/cabinet">кабинете</a> и в Telegram-боте.
          </p>
        </>
      ) : (
        <p className="paysuccess__lead">
          Подписка активирована. Ссылка доступна в <a href="/cabinet">кабинете</a> и в
          Telegram-боте @unlkvpn_bot.
        </p>
      )}
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { CopyButton } from "@/components/ui/CopyButton";
import { Pill } from "@/components/ui/Pill";
import { formatDate } from "@/lib/format";
import { botLink } from "@/lib/site";

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

/** Есть только у заказов по почте без входа. */
interface OrderAccount {
  email: string;
  isNew: boolean;
  canSetPassword: boolean;
}

const SPAM_HINT = "Письма нет? Загляните в папку «Спам» — иногда оно попадает туда.";

type Phase = "loading" | "waiting" | "done" | "no-order" | "timeout";

export function SuccessClient() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [subscription, setSubscription] = useState<OrderSubscription | null>(null);
  const [account, setAccount] = useState<OrderAccount | null>(null);
  const [orderRef, setOrderRef] = useState<string | null>(null);
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
    setOrderRef(orderId);

    async function poll(id: string) {
      if (stopped.current) return;
      try {
        const res = await fetch(`/api/order/${encodeURIComponent(id)}`, { cache: "no-store" });
        if (res.ok) {
          const body = (await res.json()) as {
            status: string;
            subscription?: OrderSubscription;
            account?: OrderAccount;
          };
          if (body.status === "succeeded" && body.subscription) {
            setSubscription(body.subscription);
            setAccount(body.account ?? null);
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
          <a href="/cabinet">кабинете</a>. Если платили по email — ссылка и данные для входа
          пришли письмом. {SPAM_HINT} Не нашли — напишите в поддержку: @unlock_support_bot.
        </p>
        <BotButton />
      </div>
    );
  }

  if (phase === "timeout") {
    return (
      <div className="paysuccess__card card">
        <Pill tone="warn">Дольше обычного</Pill>
        <h1>Платёж ещё обрабатывается</h1>
        <p className="paysuccess__lead">
          Обновите страницу через пару минут. Если оплатили через Telegram — конфиг придёт в бот,
          по email — на почту. {SPAM_HINT} Не пришёл за 15 минут — напишите в поддержку:
          @unlock_support_bot.
        </p>
      </div>
    );
  }

  const subUrl = subscription?.subscriptionUrl ?? null;

  if (account && !account.isNew) {
    // Оплата легла на уже существующий аккаунт: ссылку видит только владелец почты.
    return (
      <div className="paysuccess__card card">
        <Pill tone="accent">Готово</Pill>
        <h1>Оплата прошла — подписка продлена</h1>
        {subscription?.planTitle && <p className="paysuccess__plan mono">{subscription.planTitle}</p>}
        <p className="paysuccess__lead">
          Подписка аккаунта <b className="paysuccess__email">{account.email}</b> активна до{" "}
          {formatDate(subscription?.expiresAt ?? null)} Ссылку для подключения мы отправили на эту
          почту, она же есть в личном кабинете.
        </p>
        <p className="paysuccess__note mono">{SPAM_HINT}</p>
        <div className="paysuccess__actions">
          <Button href="/cabinet">Войти в кабинет</Button>
          <BotButton />
        </div>
      </div>
    );
  }

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
        </>
      ) : (
        <p className="paysuccess__lead">
          Подписка активирована. Ссылка доступна в <a href="/cabinet">кабинете</a> и в
          Telegram-боте.
        </p>
      )}

      {account && orderRef && <NewAccount account={account} orderRef={orderRef} />}

      <div className="paysuccess__bot">
        <BotButton />
        <p className="paysuccess__note mono">
          Отправьте боту /link и ссылку выше — подписка появится и в Telegram.
        </p>
      </div>

      <p className="paysuccess__note mono">
        Сохраните ссылку — она же доступна в <a href="/cabinet">кабинете</a>
        {account ? " и в письме на почту. " + SPAM_HINT : "."}
      </p>
    </div>
  );
}

function BotButton() {
  return (
    <Button href={botLink()} variant="ghost">
      Открыть Telegram-бота
    </Button>
  );
}

/** Кабинет создан этой оплатой: пароль ушёл письмом, но можно сразу задать свой. */
function NewAccount({ account, orderRef }: { account: OrderAccount; orderRef: string }) {
  const [password, setPassword] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (password.length < 8) {
      setError("Пароль должен быть не короче 8 символов.");
      return;
    }
    setError(null);
    setState("saving");
    try {
      const res = await fetch(`/api/order/${encodeURIComponent(orderRef)}/password`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        setError(
          body.error === "password_change_not_allowed"
            ? "Пароль уже изменён. Войдите в кабинет с ним или нажмите «Забыли пароль?»."
            : body.error === "rate_limited"
              ? "Слишком много попыток. Подождите несколько минут."
              : "Не удалось сохранить. Попробуйте ещё раз.",
        );
        setState("idle");
        return;
      }
      setState("saved");
    } catch {
      setError("Сеть недоступна. Попробуйте ещё раз.");
      setState("idle");
    }
  }

  return (
    <section className="paysuccess__account" aria-labelledby="paysuccess-account">
      <h2 id="paysuccess-account" className="paysuccess__account-title">
        Личный кабинет создан
      </h2>
      <p className="paysuccess__account-text">
        Логин — <b className="paysuccess__email">{account.email}</b>. Временный пароль мы отправили
        на эту почту.
      </p>
      {state === "saved" ? (
        <p className="paysuccess__account-text">
          ✅ Пароль сохранён, вы вошли. <a href="/cabinet">Открыть кабинет →</a>
        </p>
      ) : account.canSetPassword ? (
        <div className="paysuccess__password">
          <label className="paysuccess__label" htmlFor="paysuccess-password">
            Или придумайте свой пароль
          </label>
          <div className="paysuccess__password-row">
            <input
              id="paysuccess-password"
              className="paysuccess__input"
              type="password"
              autoComplete="new-password"
              placeholder="8+ символов"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void save()}
              disabled={state === "saving"}
            />
            <Button onClick={() => void save()} disabled={state === "saving"}>
              {state === "saving" ? "Сохраняем…" : "Сохранить и войти"}
            </Button>
          </div>
          {error && <p className="paysuccess__error">{error}</p>}
        </div>
      ) : null}
    </section>
  );
}

import type { Metadata } from "next";
import { cookies, headers } from "next/headers";

import { CabinetCards } from "@/components/cabinet/CabinetCards";
import { Logo } from "@/components/ui/Logo";
import { Pill } from "@/components/ui/Pill";
import { getAccountByTelegram, getAccountOverview, isBillingLive } from "@/lib/billing/client";
import { telegramLoginUrl } from "@/lib/telegram-auth";
import { USER_SESSION_COOKIE, verifyUserSession } from "@/lib/web-session";
import { CabinetLogin } from "./CabinetLogin";
import { LogoutButton } from "./LogoutButton";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Личный кабинет",
  robots: { index: false, follow: false },
};

// Standalone design preview (no billing API): render the demo account.
const DEMO_USER_ID = 1;

export default async function CabinetPage() {
  const telegramId = verifyUserSession(cookies().get(USER_SESSION_COOKIE)?.value);
  // Taken from the request, not from NEXT_PUBLIC_SITE_URL: Telegram rejects the
  // login when `origin` does not match the domain the person is actually on,
  // and that variable is currently set to a domain that does not resolve.
  const host = headers().get("x-forwarded-host") ?? headers().get("host") ?? "unlockvpn.site";
  const proto = headers().get("x-forwarded-proto") ?? "https";
  const tgHref = telegramLoginUrl(`${proto}://${host}/auth/telegram/callback`);

  if (!isBillingLive) {
    const demo = await getAccountOverview(DEMO_USER_ID);
    return (
      <CabinetShell headerNote={<DemoNote />} greetingId={demo.telegramId}>
        <CabinetCards account={demo} />
      </CabinetShell>
    );
  }

  if (!telegramId) {
    return (
      <CabinetShell>
        <CabinetLogin telegramLoginHref={tgHref} />
      </CabinetShell>
    );
  }

  const account = await getAccountByTelegram(telegramId);
  if (!account) {
    return (
      <CabinetShell>
        <CabinetLogin
          telegramLoginHref={tgHref}
          note="Мы не нашли аккаунт с этим Telegram. Нажмите /start в боте @unlkvpn_bot или купите подписку на сайте — аккаунт появится автоматически."
        />
      </CabinetShell>
    );
  }

  return (
    <CabinetShell greetingId={account.telegramId} showLogout>
      <CabinetCards account={account} />
    </CabinetShell>
  );
}

function CabinetShell({
  children,
  headerNote,
  greetingId,
  showLogout = false,
}: {
  children: React.ReactNode;
  headerNote?: React.ReactNode;
  greetingId?: number;
  showLogout?: boolean;
}) {
  return (
    <main id="main" className="cab">
      <div className="container">
        <div className="cab__topbar">
          <Logo />
          <a href="/" className="cab__back">
            ← На главную
          </a>
        </div>

        {headerNote}

        <header className="cab__header">
          <h1 className="cab__greeting">Личный кабинет</h1>
          {greetingId !== undefined && <p className="cab__sub mono">id: {greetingId}</p>}
          {showLogout && <LogoutButton />}
        </header>

        {children}
      </div>
    </main>
  );
}

function DemoNote() {
  return (
    <div className="cab__demo">
      <Pill tone="warn">demo</Pill>
      <span>Демонстрационные данные — биллинг не подключён (BILLING_API_URL не задан).</span>
    </div>
  );
}

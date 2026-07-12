import type { Metadata } from "next";
import { cookies } from "next/headers";
import QRCode from "qrcode";

import { CabinetCards } from "@/components/cabinet/CabinetCards";
import { Logo } from "@/components/ui/Logo";
import { Pill } from "@/components/ui/Pill";
import { getAccountByTelegram, getAccountOverview, isBillingLive } from "@/lib/billing/client";
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
        <CabinetLogin />
      </CabinetShell>
    );
  }

  const account = await getAccountByTelegram(telegramId);
  if (!account) {
    return (
      <CabinetShell>
        <CabinetLogin
          note="Мы не нашли аккаунт с этим Telegram. Нажмите /start в боте @unlkvpn_bot или купите подписку на сайте — аккаунт появится автоматически."
        />
      </CabinetShell>
    );
  }

  const subUrl = account.subscription.subscriptionUrl;
  const subscriptionQr = subUrl
    ? await QRCode.toDataURL(subUrl, { margin: 1, width: 320 })
    : null;

  return (
    <CabinetShell greetingId={account.telegramId} showLogout>
      <CabinetCards account={account} subscriptionQr={subscriptionQr} />
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

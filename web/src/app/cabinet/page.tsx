import type { Metadata } from "next";

import { CabinetCards } from "@/components/cabinet/CabinetCards";
import { Logo } from "@/components/ui/Logo";
import { Pill } from "@/components/ui/Pill";
import { getAccountOverview, isBillingLive } from "@/lib/billing/client";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Личный кабинет",
  robots: { index: false, follow: false },
};

// Demo identity until Telegram Login / email auth is wired (Phase 3, item 33).
const DEMO_USER_ID = 1;

export default async function CabinetPage() {
  const account = await getAccountOverview(DEMO_USER_ID);

  return (
    <main id="main" className="cab">
      <div className="container">
        <div className="cab__topbar">
          <Logo />
          <a href="/" className="cab__back">
            ← На главную
          </a>
        </div>

        {!isBillingLive && (
          <div className="cab__demo">
            <Pill tone="warn">demo</Pill>
            <span>
              Демонстрационные данные. Вход через Telegram / email и живой биллинг
              подключаются на следующем шаге.
            </span>
          </div>
        )}

        <header className="cab__header">
          <h1 className="cab__greeting">Личный кабинет</h1>
          <p className="cab__sub mono">id: {account.telegramId}</p>
        </header>

        <CabinetCards account={account} />
      </div>
    </main>
  );
}

import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Logo } from "@/components/ui/Logo";
import { TARIFFS } from "@/lib/tariffs";
import { BuyClient } from "./BuyClient";
import "./buy.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Оплата подписки",
  robots: { index: false, follow: false },
};

export default function BuyPage({
  searchParams,
}: {
  searchParams: { plan?: string };
}) {
  const plan = TARIFFS[searchParams.plan ?? ""];
  if (!plan || plan.tier !== "standard") {
    redirect("/#pricing");
  }

  return (
    <main id="main" className="buy">
      <div className="container buy__container">
        <div className="buy__topbar">
          <Logo />
          <a href="/#pricing" className="buy__back">
            ← К тарифам
          </a>
        </div>

        <BuyClient
          planCode={plan.code}
          planTitle={plan.title}
          priceRub={plan.priceRub}
          trafficGb={plan.trafficGb}
          trafficResetsMonthly={plan.trafficResetsMonthly}
          deviceLimit={plan.deviceLimit}
        />
      </div>
    </main>
  );
}

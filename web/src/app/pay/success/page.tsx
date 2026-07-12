import type { Metadata } from "next";

import { Logo } from "@/components/ui/Logo";
import { SuccessClient } from "./SuccessClient";
import "./success.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Оплата — получение конфига",
  robots: { index: false, follow: false },
};

export default function PaySuccessPage() {
  return (
    <main id="main" className="paysuccess">
      <div className="container paysuccess__container">
        <div className="paysuccess__topbar">
          <Logo />
          <a href="/" className="paysuccess__back">
            ← На главную
          </a>
        </div>

        <SuccessClient />
      </div>
    </main>
  );
}

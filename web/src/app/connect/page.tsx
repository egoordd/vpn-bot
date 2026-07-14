import type { Metadata } from "next";

import { Logo } from "@/components/ui/Logo";
import { ConnectClient } from "./ConnectClient";
import "./connect.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Подключение VPN",
  description: "Как подключить UnLock VPN: импортируйте ссылку-подписку в приложение за пару тапов.",
  robots: { index: false, follow: false },
};

export default function ConnectPage() {
  return (
    <main id="main" className="connectp">
      <div className="container connectp__container">
        <div className="connectp__topbar">
          <Logo />
          <a href="/" className="connectp__back">
            ← На главную
          </a>
        </div>

        <ConnectClient />
      </div>
    </main>
  );
}

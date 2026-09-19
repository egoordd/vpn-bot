import type { Metadata } from "next";

import { Logo } from "@/components/ui/Logo";
import { ResetClient } from "./ResetClient";
import "@/components/cabinet/cabinet.css";

export const metadata: Metadata = {
  title: "Новый пароль",
  robots: { index: false, follow: false },
};

/** Сюда ведёт ссылка из письма «Забыли пароль?»; токен — во фрагменте адреса. */
export default function ResetPasswordPage() {
  return (
    <main id="main" className="cab">
      <div className="container">
        <div className="cab__topbar">
          <Logo />
          <a href="/cabinet" className="cab__back">
            ← В кабинет
          </a>
        </div>
        <ResetClient />
      </div>
    </main>
  );
}

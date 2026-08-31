import type { Metadata } from "next";

import { CallbackClient } from "./CallbackClient";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Вход через Telegram",
  robots: { index: false, follow: false },
};

/**
 * Where Telegram sends people back after they confirm the login.
 *
 * The signed payload arrives in the URL fragment, which browsers never send to
 * the server, so the exchange has to happen in the page: read the fragment,
 * hand it to /api/auth/telegram, which checks the signature against the bot
 * token and sets the session cookie.
 */
export default function TelegramCallbackPage() {
  return (
    <main id="main" className="cab">
      <div className="container">
        <CallbackClient />
      </div>
    </main>
  );
}

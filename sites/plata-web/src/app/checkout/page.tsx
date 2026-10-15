import type { Metadata } from "next";

import { Checkout } from "@/components/checkout/Checkout";
import { Footer, Header } from "@/components/nav/Nav";
import { SITE } from "@/lib/site";
import "@/components/legal/legal.css";

export const metadata: Metadata = {
  title: "Оформление подписки",
  description: `Оформление подписки ${SITE.name}: выбор срока, адрес почты и способ оплаты.`,
};

export default function CheckoutPage() {
  return (
    <>
      <Header />
      <main id="main" className="legal">
        <div className="wrap">
          <header className="legal__head" style={{ marginBottom: "2.5rem" }}>
            <span className="eyebrow">Тарифы</span>
            <h1>Оформление подписки</h1>
            <p className="legal__intro">Выберите срок, укажите почту — на неё придут чек и доступ.</p>
          </header>
          <Checkout />
        </div>
      </main>
      <Footer />
    </>
  );
}

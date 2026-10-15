import type { Metadata, Viewport } from "next";
import { Comfortaa, Nunito } from "next/font/google";
import type { ReactNode } from "react";

import { SITE } from "@/lib/site";
import "./globals.css";

/* Comfortaa — заголовки прописными, как в листе «Замок»; Nunito — текст (строчная кириллица Comfortaa читается плохо). */
const comfortaa = Comfortaa({ subsets: ["latin", "cyrillic"], weight: ["600", "700"], display: "swap", variable: "--font-comfortaa" });
const nunito = Nunito({ subsets: ["latin", "cyrillic"], display: "swap", variable: "--font-nunito" });

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: `${SITE.name} — ${SITE.tagline}`, template: `%s · ${SITE.name}` },
  description: SITE.description,
  applicationName: SITE.name,
  openGraph: {
    title: `${SITE.name} — ${SITE.tagline}`,
    description: SITE.description,
    type: "website",
    locale: "ru_RU",
    siteName: SITE.name,
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = { themeColor: "#0B231B", colorScheme: "dark" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" className={`${comfortaa.variable} ${nunito.variable}`}>
      <body>{children}</body>
    </html>
  );
}

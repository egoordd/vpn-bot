import type { Metadata, Viewport } from "next";
import { Onest } from "next/font/google";
import type { ReactNode } from "react";

import { SITE } from "@/lib/site";
import "./globals.css";

/* Onest — мягкий гротеск с кириллицей, близкий к надписи «Plata» на логотипе. */
const onest = Onest({ subsets: ["latin", "cyrillic"], display: "swap", variable: "--font-onest" });

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

export const viewport: Viewport = { themeColor: "#FEF8EC", colorScheme: "light" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" className={onest.variable}>
      <body>{children}</body>
    </html>
  );
}

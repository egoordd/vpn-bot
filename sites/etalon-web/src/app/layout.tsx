import type { Metadata, Viewport } from "next";
import { Cormorant_Garamond, Manrope } from "next/font/google";

import { SITE } from "@/lib/site";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin", "cyrillic"], display: "swap", variable: "--font-manrope" });
const cormorant = Cormorant_Garamond({
  subsets: ["latin", "cyrillic"],
  weight: ["500", "600"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-cormorant",
});

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

export const viewport: Viewport = { themeColor: "#F5F8FC", colorScheme: "light" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={`${manrope.variable} ${cormorant.variable}`}>
      <body>
        <a href="#main" className="skip-link">
          К основному содержимому
        </a>
        {children}
      </body>
    </html>
  );
}

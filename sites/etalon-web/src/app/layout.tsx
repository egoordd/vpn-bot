import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";

import { SITE } from "@/lib/site";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin", "cyrillic"], display: "swap", variable: "--font-manrope" });
// Фирменный M PLUS Rounded 1c подключён файлами из public/fonts (styles/fonts.css): у Google он
// разбит на 378 кусков с японскими иероглифами, а нам нужны только латиница и кириллица.

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

export const viewport: Viewport = { themeColor: "#E8F2FF", colorScheme: "light" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={manrope.variable}>
      <body>
        <a href="#main" className="skip-link">
          К основному содержимому
        </a>
        {children}
      </body>
    </html>
  );
}

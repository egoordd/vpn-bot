export const SITE = {
  name: "UnLock",
  tagline: "Интернет без границ — просто и надёжно",
  description:
    "UnLock — надёжный VPN с подпиской. Подключение за минуту, работает на телефоне и компьютере, не обрывается. Оплата удобными способами.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "unlock_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://unlock.example",
  // Support mailbox shown on the site. Own-domain address by default; set up
  // Cloudflare Email Routing (free) to forward it to your real inbox, or point
  // NEXT_PUBLIC_SUPPORT_EMAIL at any working address.
  supportEmail: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "support@unlockvpn.site",
} as const;

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

export const NAV_LINKS = [
  { href: "#features", label: "Возможности" },
  { href: "#pricing", label: "Тарифы" },
  { href: "#how", label: "Как это работает" },
  { href: "#faq", label: "Вопросы" },
] as const;

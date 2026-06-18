export const SITE = {
  name: "UnLock",
  tagline: "Интернет без границ — просто и надёжно",
  description:
    "UnLock — надёжный VPN с подпиской. Подключение за минуту, работает на телефоне и компьютере, не обрывается. Оплата картой или криптой.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "unlock_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://unlock.example",
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

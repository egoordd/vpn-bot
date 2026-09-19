export const SITE = {
  name: "UnLock",
  tagline: "Интернет без границ — просто и надёжно",
  description:
    "UnLock — надёжный VPN с подпиской. Подключение за минуту, работает на телефоне и компьютере, не обрывается. Оплата удобными способами.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "unlkvpn_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://unlock.example",
  // Support mailbox shown on the site: the inbox our letters are sent from, so
  // a reply to a purchase letter and a message from the site land together.
  // The old unlockvpn.site zone has no mail server — mail there bounced.
  supportEmail: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "unlockvpnru@gmail.com",
} as const;

/** Кампания, по ссылке которой пришёл посетитель. Ставится /go/<кампания>,
 *  читается при регистрации и оплате — иначе покупатель с сайта остаётся без
 *  канала, а это большая часть выручки. */
export const SOURCE_COOKIE = "unlock_src";

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

export const NAV_LINKS = [
  { href: "/#features", label: "Возможности" },
  { href: "/#pricing", label: "Тарифы" },
  { href: "/#how", label: "Как это работает" },
  { href: "/download", label: "Установка" },
  { href: "/#faq", label: "Вопросы" },
] as const;

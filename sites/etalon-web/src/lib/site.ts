export const SITE = {
  name: "Etalon VPN",
  tagline: "Эталон свободного интернета",
  description:
    "Etalon VPN — быстрый и стабильный VPN для телефона и компьютера. Четыре страны, автоматический выбор сервера, российские сервисы без отключения VPN. 3 дня бесплатно.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "etallonvpn_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://etalon.example",
} as const;

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

export const NAV_LINKS = [
  { href: "/#features", label: "Возможности" },
  { href: "/#pricing", label: "Тарифы" },
  { href: "/#how", label: "Как подключить" },
  { href: "/#faq", label: "Вопросы" },
] as const;

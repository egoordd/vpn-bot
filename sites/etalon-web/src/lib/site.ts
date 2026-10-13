export const SITE = {
  name: "Etalon VPN",
  tagline: "билет в свободный интернет",
  description:
    "Etalon VPN — VPN первого класса для телефона и компьютера: четыре страны, автопилот выбирает быстрый сервер, российские сервисы работают без отключения VPN. 3 дня бесплатно.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "etallonvpn_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://etalon.168.113.210.6.sslip.io",
} as const;

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

export const NAV_LINKS = [
  { href: "#routes", label: "Направления" },
  { href: "#onboard", label: "На борту" },
  { href: "#checkin", label: "Регистрация" },
  { href: "#tickets", label: "Билеты" },
  { href: "#help", label: "Справочная" },
] as const;

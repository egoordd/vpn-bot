export const SITE = {
  name: "Etalon VPN",
  tagline: "интернет, каким он должен быть",
  description:
    "Etalon VPN — частная сеть премиум-класса: быстрые серверы в четырёх странах, автоматический выбор маршрута и российские сервисы без отключения VPN. 3 дня бесплатно.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "etallonvpn_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://etalon.168.113.210.6.sslip.io",
} as const;

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

export const NAV_LINKS = [
  { href: "#features", label: "Преимущества" },
  { href: "#connect", label: "Подключение" },
  { href: "#pricing", label: "Тарифы" },
  { href: "#faq", label: "Вопросы" },
] as const;

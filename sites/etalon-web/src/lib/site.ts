export const SITE = {
  name: "Etalon VPN",
  tagline: "интернет, каким он должен быть",
  description:
    "Etalon VPN — частная сеть премиум-класса: быстрые серверы в четырёх странах, автоматический выбор маршрута и российские сервисы без отключения VPN. 3 дня бесплатно.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "etallonvpn_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://getetalon.site",
} as const;

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

/* Ссылки ведут на разделы главной — с «/», чтобы работали и со страниц документов. */
export const NAV_LINKS = [
  { href: "/#features", label: "Преимущества" },
  { href: "/#connect", label: "Подключение" },
  { href: "/#pricing", label: "Тарифы" },
  { href: "/#faq", label: "Вопросы" },
] as const;

/* Документы и контакты — их требует платёжный провайдер; должны быть доступны всегда. */
export const LEGAL_LINKS = [
  { href: "/tariffs/", label: "Тарифы и оплата" },
  { href: "/terms/", label: "Пользовательское соглашение" },
  { href: "/privacy/", label: "Политика конфиденциальности" },
  { href: "/support/", label: "Поддержка" },
] as const;

export const SUPPORT = {
  /* Обращение открывается кнопкой «Поддержка» в боте: сообщение уходит администрации, ответ приходит туда же. */
  botLink: botLink("support"),
  email: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "",
  replyHours: 24,
} as const;

/* Дата редакции документов. */
export const LEGAL_UPDATED = "13 октября 2026 г.";

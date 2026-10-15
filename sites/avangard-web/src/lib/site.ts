/* Avangard VPN (третий заказчик): бот @avangardgt_bot, сайт на 168.113.210.6. Фирменный лист «Замок». */
export const SITE = {
  name: "Avangard VPN",
  tagline: "Ваша крепость в интернете",
  description:
    "Avangard VPN — защищённое соединение через Германию и Нидерланды. Авто-выбор держит самый быстрый сервер, до 5 устройств, бот на пяти языках. 3 дня бесплатно.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "avangardgt_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://avangard.168.113.210.6.sslip.io",
} as const;

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

/* Серверы — как выдаёт шлюз учёткам corp_avg_* (14.10.2026): две страны и авто-выбор между ними. */
export const TOWERS = [
  { flag: "🇩🇪", name: "Германия", code: "DE" },
  { flag: "🇳🇱", name: "Нидерланды", code: "NL" },
] as const;

/* Языки интерфейса бота. */
export const LANGUAGES = [
  { flag: "🇷🇺", name: "Русский" },
  { flag: "🇬🇧", name: "English" },
  { flag: "🇺🇦", name: "Українська" },
  { flag: "🇨🇳", name: "中文" },
  { flag: "🇮🇷", name: "فارسی" },
] as const;

export const NAV_LINKS = [
  { href: "/#walls", label: "Защита" },
  { href: "/#towers", label: "Серверы" },
  { href: "/#pricing", label: "Тарифы" },
  { href: "/#faq", label: "Вопросы" },
] as const;

export const LEGAL_LINKS = [
  { href: "/tariffs/", label: "Тарифы и оплата" },
  { href: "/terms/", label: "Пользовательское соглашение" },
  { href: "/privacy/", label: "Политика конфиденциальности" },
  { href: "/support/", label: "Поддержка" },
] as const;

export const SUPPORT = {
  botLink: botLink("support"),
  email: process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "",
  replyHours: 24,
} as const;

/* Реквизиты исполнителя — когда пришлёт заказчик; пусто — блок не показывается. */
export const REQUISITES: readonly string[] = [];

export const LEGAL_UPDATED = "15 октября 2026 г.";

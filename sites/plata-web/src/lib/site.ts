/* Plata VPN (заказчик Ярослав): бот @plataavpn_bot, сайт на 168.113.210.6. */
export const SITE = {
  name: "Plata VPN",
  short: "Plata",
  tagline: "Безопасный и быстрый интернет",
  description:
    "Plata VPN шифрует соединение и сама выбирает самый быстрый сервер. Банки и Госуслуги работают, не выключая VPN. 3 дня бесплатно.",
  botUsername: process.env.NEXT_PUBLIC_TELEGRAM_BOT ?? "plataavpn_bot",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "https://plata.168.113.210.6.sslip.io",
} as const;

export function botLink(payload?: string): string {
  const base = `https://t.me/${SITE.botUsername}`;
  return payload ? `${base}?start=${payload}` : base;
}

export const COUNTRIES = [
  { flag: "🇵🇱", name: "Польша" },
  { flag: "🇫🇮", name: "Финляндия" },
  { flag: "🇳🇱", name: "Нидерланды" },
  { flag: "🇺🇸", name: "США" },
] as const;

/* Ссылки ведут на разделы главной — с «/», чтобы работали и со страниц документов. */
export const NAV_LINKS = [
  { href: "/#levels", label: "Защита" },
  { href: "/#connect", label: "Подключение" },
  { href: "/#pricing", label: "Тарифы" },
  { href: "/#faq", label: "Вопросы" },
] as const;

/* Документы и контакты — их проверяет платёжный сервис; должны быть доступны всегда. */
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

/* Реквизиты исполнителя (ФИО, статус, ИНН) — когда пришлёт заказчик; пусто — блок не показывается. */
export const REQUISITES: readonly string[] = [];

/* Способы оплаты на странице платёжного сервиса. */
export const PAY_METHODS = "банковской картой, через СБП или SberPay";

/* Дата редакции документов. */
export const LEGAL_UPDATED = "15 октября 2026 г.";

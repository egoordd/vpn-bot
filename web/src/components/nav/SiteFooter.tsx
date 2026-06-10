import { Logo } from "@/components/ui/Logo";
import { SITE, botLink } from "@/lib/site";
import "./site-footer.css";

const COLUMNS = [
  {
    title: "Продукт",
    links: [
      { href: "#features", label: "Возможности" },
      { href: "#pricing", label: "Тарифы" },
      { href: "#how", label: "Как это работает" },
      { href: "/cabinet", label: "Личный кабинет" },
    ],
  },
  {
    title: "Поддержка",
    links: [
      { href: "#faq", label: "Частые вопросы" },
      { href: botLink(), label: "Написать в бота" },
      { href: "#", label: "Статус сервиса" },
    ],
  },
  {
    title: "Правовое",
    links: [
      { href: "#", label: "Условия использования" },
      { href: "#", label: "Политика конфиденциальности" },
      { href: "#", label: "Оферта" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="footer">
      <div className="container footer__inner">
        <div className="footer__brand">
          <Logo />
          <p className="footer__tagline">
            {SITE.tagline}. Доступ без VPN — на чистом домене и зеркалах.
          </p>
          <p className="footer__signal mono">
            <span className="footer__signal-dot" aria-hidden /> Сеть работает
          </p>
        </div>

        <div className="footer__cols">
          {COLUMNS.map((col) => (
            <nav key={col.title} className="footer__col" aria-label={col.title}>
              <h4 className="footer__col-title">{col.title}</h4>
              <ul>
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a className="footer__link" href={link.href}>
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
      </div>

      <div className="container footer__bottom">
        <span className="mono">© {new Date().getFullYear()} {SITE.name}</span>
        <span className="footer__note mono">Не для обхода закона. Используй ответственно.</span>
      </div>
    </footer>
  );
}

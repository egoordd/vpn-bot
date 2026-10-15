import { LANGUAGES, LEGAL_LINKS, NAV_LINKS, REQUISITES, SITE, SUPPORT, botLink } from "@/lib/site";
import { TRIAL_DAYS_LABEL } from "@/lib/tariffs";
import { Button, Logo } from "../ui/ui";
import "./nav.css";

export function Header() {
  return (
    <header className="top">
      <div className="wrap top__row">
        <Logo />
        <nav className="top__nav" aria-label="Разделы">
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href}>
              {link.label}
            </a>
          ))}
        </nav>
        <Button href={botLink("site")} variant="outline" external>
          <span className="top__cta-long">{TRIAL_DAYS_LABEL} бесплатно</span>
          <span className="top__cta-short">Начать</span>
        </Button>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="foot">
      <div className="wrap foot__grid">
        <div className="foot__brand">
          <Logo />
          <p>{SITE.tagline}. Доступ выдаёт Telegram-бот @{SITE.botUsername}.</p>
          <p className="foot__langs" aria-label="Языки бота">
            {LANGUAGES.map((lang) => (
              <span key={lang.name}>
                {lang.flag} {lang.name}
              </span>
            ))}
          </p>
        </div>
        <nav className="foot__col" aria-label="Документы">
          <span className="foot__title">Документы</span>
          {LEGAL_LINKS.map((link) => (
            <a key={link.href} href={link.href}>
              {link.label}
            </a>
          ))}
        </nav>
        <div className="foot__col">
          <span className="foot__title">Связь</span>
          <a href={SUPPORT.botLink} target="_blank" rel="noopener noreferrer">
            Поддержка в боте
          </a>
          {SUPPORT.email && <a href={`mailto:${SUPPORT.email}`}>{SUPPORT.email}</a>}
          <a href={botLink()} target="_blank" rel="noopener noreferrer">
            @{SITE.botUsername}
          </a>
          <span className="foot__muted">Ответ — до {SUPPORT.replyHours} часов</span>
        </div>
      </div>
      <div className="wrap foot__bottom">
        <span>© 2026 {SITE.name}</span>
        {REQUISITES.length > 0 && <span>{REQUISITES.join(" · ")}</span>}
        <span>Оплата разовая, без автосписаний</span>
      </div>
    </footer>
  );
}

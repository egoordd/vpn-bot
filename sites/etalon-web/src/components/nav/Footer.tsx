import { Logo } from "@/components/ui/Logo";
import { LEGAL_LINKS, NAV_LINKS, SITE, botLink } from "@/lib/site";
import "./footer.css";

export function Footer() {
  return (
    <footer className="ftr">
      <div className="container ftr__row">
        <div className="ftr__brand">
          <Logo />
          <p>
            Интернет, <em>каким он должен быть</em>.
          </p>
        </div>
        <nav className="ftr__nav" aria-label="Разделы">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
          <a href={botLink()} target="_blank" rel="noopener noreferrer">
            Telegram-бот
          </a>
        </nav>
      </div>
      <nav className="container ftr__legal" aria-label="Документы">
        {LEGAL_LINKS.map((l) => (
          <a key={l.href} href={l.href}>
            {l.label}
          </a>
        ))}
      </nav>
      <div className="container ftr__bottom">
        <span>© {new Date().getFullYear()} {SITE.name}</span>
        <span>Используйте сервис ответственно и в рамках закона.</span>
      </div>
    </footer>
  );
}

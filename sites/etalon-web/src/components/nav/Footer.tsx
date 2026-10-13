import { Logo } from "@/components/ui/Logo";
import { NAV_LINKS, SITE, botLink } from "@/lib/site";
import "./footer.css";

export function Footer() {
  return (
    <footer className="ftr">
      <div className="container ftr__row">
        <div className="ftr__brand">
          <Logo />
          <p>Etalon VPN — {SITE.tagline}.</p>
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
      <div className="container ftr__bottom">
        <span>© {new Date().getFullYear()} {SITE.name}</span>
        <span>Используйте сервис ответственно и в рамках закона.</span>
      </div>
    </footer>
  );
}

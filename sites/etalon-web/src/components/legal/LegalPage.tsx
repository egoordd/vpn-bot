import { Footer } from "@/components/nav/Footer";
import { Header } from "@/components/nav/Header";
import { LEGAL_LINKS, LEGAL_UPDATED } from "@/lib/site";
import "./legal.css";

interface LegalPageProps {
  overline: string;
  title: string;
  /** Адрес страницы (`/terms/`) — подсвечивает её в списке документов. */
  path: string;
  /** Короткий абзац под заголовком. */
  intro?: React.ReactNode;
  children: React.ReactNode;
}

/** Страница документа: шапка сайта, заголовок антиквой, текст в удобной колонке и список всех документов сбоку. */
export function LegalPage({ overline, title, path, intro, children }: LegalPageProps) {
  return (
    <>
      <Header />
      <main id="main" className="legal">
        <div className="container legal__grid">
          <header className="legal__head">
            <span className="overline">{overline}</span>
            <h1>{title}</h1>
            {intro && <p className="lead legal__intro">{intro}</p>}
            <p className="legal__updated">Редакция от {LEGAL_UPDATED}</p>
          </header>

          <article className="legal__body">{children}</article>

          <aside className="legal__aside" aria-label="Документы">
            <span className="legal__aside-title">Документы</span>
            <nav>
              {LEGAL_LINKS.map((l) => (
                <a key={l.href} href={l.href} aria-current={l.href === path ? "page" : undefined}>
                  {l.label}
                </a>
              ))}
            </nav>
          </aside>
        </div>
      </main>
      <Footer />
    </>
  );
}

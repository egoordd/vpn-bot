import type { ReactNode } from "react";

import { LEGAL_LINKS, LEGAL_UPDATED } from "@/lib/site";
import { Footer, Header } from "../nav/Nav";
import "./legal.css";

interface LegalPageProps {
  overline: string;
  title: string;
  /** Адрес страницы (`/terms/`) — подсвечивает её в списке документов. */
  path: string;
  intro?: ReactNode;
  children: ReactNode;
}

/** Страница документа: заголовок, текст в удобной колонке и список всех документов сбоку. */
export function LegalPage({ overline, title, path, intro, children }: LegalPageProps) {
  return (
    <>
      <Header />
      <main id="main" className="legal">
        <div className="wrap legal__grid">
          <header className="legal__head">
            <span className="eyebrow">{overline}</span>
            <h1>{title}</h1>
            {intro && <p className="legal__intro">{intro}</p>}
            <p className="legal__updated">Редакция от {LEGAL_UPDATED}</p>
          </header>
          <article className="legal__body">{children}</article>
          <aside className="legal__aside" aria-label="Документы">
            <span className="legal__aside-title">Документы</span>
            <nav>
              {LEGAL_LINKS.map((link) => (
                <a key={link.href} href={link.href} aria-current={link.href === path ? "page" : undefined}>
                  {link.label}
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

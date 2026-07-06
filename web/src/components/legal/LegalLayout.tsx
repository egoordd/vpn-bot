import type { ReactNode } from "react";

import { SiteFooter } from "@/components/nav/SiteFooter";
import { SiteNav } from "@/components/nav/SiteNav";
import "./legal.css";

interface LegalLayoutProps {
  title: string;
  updated: string;
  children: ReactNode;
}

export function LegalLayout({ title, updated, children }: LegalLayoutProps) {
  return (
    <>
      <SiteNav />
      <main id="main" className="legal">
        <div className="container legal__inner">
          <a href="/" className="legal__back">
            ← На главную
          </a>
          <h1 className="legal__title">{title}</h1>
          <p className="legal__updated">Редакция от {updated}</p>
          <div className="legal__body">{children}</div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}

/** Placeholder for data the merchant fills in (highlighted in the rendered doc). */
export function Fill({ children }: { children: ReactNode }) {
  return <span className="legal__fill">{children}</span>;
}

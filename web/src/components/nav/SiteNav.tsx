"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { cn } from "@/lib/cn";
import { NAV_LINKS, botLink } from "@/lib/site";
import "./site-nav.css";

export function SiteNav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <header className={cn("nav", scrolled && "nav--scrolled")}>
      <div className="container nav__inner">
        <Logo />

        <nav className="nav__links" aria-label="Основная навигация">
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href} className="nav__link">
              {link.label}
            </a>
          ))}
        </nav>

        <div className="nav__actions">
          <a href="/cabinet" className="nav__link nav__link--cabinet">
            Кабинет
          </a>
          <Button href={botLink()} size="md">
            Подключить
          </Button>
        </div>

        <button
          className="nav__burger"
          aria-label={open ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span className={cn("nav__burger-bar", open && "is-open-1")} />
          <span className={cn("nav__burger-bar", open && "is-open-2")} />
        </button>
      </div>

      {open && (
        <div className="nav__drawer" role="dialog" aria-modal="true">
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href} className="nav__drawer-link" onClick={() => setOpen(false)}>
              {link.label}
            </a>
          ))}
          <a href="/cabinet" className="nav__drawer-link" onClick={() => setOpen(false)}>
            Личный кабинет
          </a>
          <Button href={botLink()} size="lg" className="nav__drawer-cta">
            Подключить за минуту
          </Button>
        </div>
      )}
    </header>
  );
}

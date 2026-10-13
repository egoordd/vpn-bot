"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { cn } from "@/lib/cn";
import { NAV_LINKS, botLink } from "@/lib/site";
import "./header.css";

export function Header() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className={cn("hdr", scrolled && "hdr--scrolled")}>
      <div className="container hdr__row">
        <Logo />
        <nav className="hdr__nav" aria-label="Основная навигация">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href}>
              {l.label}
            </a>
          ))}
        </nav>
        <Button href={botLink()} size="md" className="hdr__cta">
          Получить билет
        </Button>
        <button
          type="button"
          className="hdr__burger"
          aria-label={open ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={open}
          aria-controls="hdr-drawer"
          onClick={() => setOpen((v) => !v)}
        >
          <span className={cn(open && "is-open")} />
        </button>
      </div>
      {open && (
        <nav id="hdr-drawer" className="hdr__drawer" aria-label="Меню">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)}>
              {l.label}
            </a>
          ))}
          <Button href={botLink()} variant="gold">
            3 дня бесплатно
          </Button>
        </nav>
      )}
    </header>
  );
}

import type { ReactNode } from "react";

import { SITE } from "@/lib/site";
import { ShieldMark } from "./ShieldMark";
import "./ui.css";

export function Logo({ tone = "navy" }: { tone?: "navy" | "light" }) {
  return (
    <a className={`logo logo--${tone}`} href="/" aria-label={`${SITE.name} — на главную`}>
      <ShieldMark className="logo__mark" />
      <span className="logo__word">{SITE.short}</span>
    </a>
  );
}

interface ButtonProps {
  href: string;
  children: ReactNode;
  variant?: "navy" | "amber" | "ghost" | "light";
  size?: "md" | "lg";
  external?: boolean;
}

export function Button({ href, children, variant = "navy", size = "md", external }: ButtonProps) {
  return (
    <a
      className={`btn btn--${variant} btn--${size}`}
      href={href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
    >
      {children}
    </a>
  );
}

/* Стрелка-шеврон в кнопках и ссылках — тот же знак, что в логотипе. */
export function Chevron({ className }: { className?: string }) {
  return (
    <svg className={className ?? "chev"} viewBox="0 0 16 16" aria-hidden="true">
      <path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

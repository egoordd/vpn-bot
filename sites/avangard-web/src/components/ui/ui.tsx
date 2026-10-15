import type { ReactNode } from "react";

import { SITE } from "@/lib/site";
import { Tower } from "./Tower";
import "./ui.css";

export function Logo() {
  return (
    <a className="logo" href="/" aria-label={`${SITE.name} — на главную`}>
      <Tower className="logo__tower" />
      <span className="logo__word">
        Avangard<small>VPN</small>
      </span>
    </a>
  );
}

interface ButtonProps {
  href: string;
  children: ReactNode;
  variant?: "gold" | "outline" | "ink";
  size?: "md" | "lg";
  external?: boolean;
}

export function Button({ href, children, variant = "gold", size = "md", external }: ButtonProps) {
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

/* Разделитель «— VPN —» из листа: строка между двумя золотыми чертами. */
export function Rule({ children }: { children: ReactNode }) {
  return <span className="rule">{children}</span>;
}

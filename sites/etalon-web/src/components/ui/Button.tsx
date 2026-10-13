import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import "./button.css";

interface ButtonProps {
  href: string;
  children: ReactNode;
  variant?: "primary" | "outline" | "link" | "gold";
  className?: string;
}

/** Кнопка-ссылка: ссылки на бот открываются в новой вкладке. */
export function Button({ href, children, variant = "primary", className }: ButtonProps) {
  const external = href.startsWith("http");
  return (
    <a
      href={href}
      className={cn("btn", `btn--${variant}`, className)}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
    >
      {children}
    </a>
  );
}

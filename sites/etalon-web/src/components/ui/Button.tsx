import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import "./button.css";

interface ButtonProps {
  href: string;
  children: ReactNode;
  variant?: "navy" | "gold" | "ghost";
  size?: "md" | "lg";
  className?: string;
}

/** Кнопка-ссылка: внешние ссылки (бот) открываются в новой вкладке. */
export function Button({ href, children, variant = "navy", size = "lg", className }: ButtonProps) {
  const external = href.startsWith("http");
  return (
    <a
      href={href}
      className={cn("btn", `btn--${variant}`, `btn--${size}`, className)}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
    >
      {children}
    </a>
  );
}

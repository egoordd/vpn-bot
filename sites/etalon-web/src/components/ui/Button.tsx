import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";
import "./button.css";

type Variant = "primary" | "ghost" | "premium";
type Size = "md" | "lg";

interface CommonProps {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
  className?: string;
}

type ButtonAsLink = CommonProps & { href: string } & Omit<
    AnchorHTMLAttributes<HTMLAnchorElement>,
    "href" | "className"
  >;
type ButtonAsButton = CommonProps & { href?: undefined } & Omit<
    ButtonHTMLAttributes<HTMLButtonElement>,
    "className"
  >;

export type ButtonProps = ButtonAsLink | ButtonAsButton;

export function Button({ variant = "primary", size = "md", className, children, ...rest }: ButtonProps) {
  const classes = cn("btn", `btn--${variant}`, `btn--${size}`, className);

  if ("href" in rest && rest.href !== undefined) {
    const { href, ...anchorRest } = rest;
    const external = href.startsWith("http");
    if (external) {
      return (
        <a className={classes} href={href} target="_blank" rel="noopener noreferrer" {...anchorRest}>
          {children}
        </a>
      );
    }
    return (
      <Link className={classes} href={href} {...anchorRest}>
        {children}
      </Link>
    );
  }

  return (
    <button className={classes} {...(rest as ButtonHTMLAttributes<HTMLButtonElement>)}>
      {children}
    </button>
  );
}

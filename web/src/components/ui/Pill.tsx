import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import "./pill.css";

type Tone = "accent" | "premium" | "warn" | "danger" | "neutral";

interface PillProps {
  tone?: Tone;
  live?: boolean;
  children: ReactNode;
  className?: string;
}

/** Status chip with an optional pulsing signal dot. */
export function Pill({ tone = "neutral", live = false, children, className }: PillProps) {
  return (
    <span className={cn("pill", `pill--${tone}`, className)}>
      {live && <span className="pill__dot" aria-hidden />}
      {children}
    </span>
  );
}

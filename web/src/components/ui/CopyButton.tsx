"use client";

import { useState } from "react";

import { cn } from "@/lib/cn";
import "./copy-button.css";

interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

export function CopyButton({ value, label = "Копировать", className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button
      type="button"
      className={cn("copy", copied && "is-copied", className)}
      onClick={handleCopy}
      aria-label={copied ? "Скопировано" : label}
    >
      {copied ? "Скопировано ✓" : label}
    </button>
  );
}

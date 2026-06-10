import Link from "next/link";

import "./logo.css";

interface LogoProps {
  href?: string;
}

/** Wordmark with a stylised open-padlock glyph. */
export function Logo({ href = "/" }: LogoProps) {
  return (
    <Link href={href} className="logo" aria-label="UnLock — на главную">
      <span className="logo__mark" aria-hidden>
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <path
            d="M7 10V7a5 5 0 0 1 9.6-2"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <rect x="4.5" y="10" width="15" height="10" rx="2.5" stroke="currentColor" strokeWidth="2" />
          <circle cx="12" cy="15" r="1.6" fill="currentColor" />
        </svg>
      </span>
      <span className="logo__word">
        Un<span className="logo__accent">Lock</span>
      </span>
    </Link>
  );
}

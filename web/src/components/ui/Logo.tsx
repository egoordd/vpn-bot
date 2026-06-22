import Link from "next/link";

import { LogoMark } from "./LogoMark";
import "./logo.css";

interface LogoProps {
  href?: string;
}

/** Wordmark: the twin-U lock glyph as the initial letter + "nlock" + muted "UPN". */
export function Logo({ href = "/" }: LogoProps) {
  return (
    <Link href={href} className="logo" aria-label="Unlock — на главную">
      <LogoMark className="logo__mark" />
      <span className="logo__word">
        nlock<span className="logo__upn">UPN</span>
      </span>
    </Link>
  );
}

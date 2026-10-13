import Link from "next/link";

import { LogoMark } from "./LogoMark";
import "./logo.css";

interface LogoProps {
  href?: string;
}

/** Знак-ключ + «ETALON» с разрядкой и приглушённое «VPN» — как в фирменном листе. */
export function Logo({ href = "/" }: LogoProps) {
  return (
    <Link href={href} className="logo" aria-label="Etalon VPN — на главную">
      <LogoMark className="logo__mark" />
      <span className="logo__word">
        ETALON<span className="logo__upn">VPN</span>
      </span>
    </Link>
  );
}

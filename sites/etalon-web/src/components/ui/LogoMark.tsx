interface LogoMarkProps {
  className?: string;
}

/** Ключ-«E» Etalon VPN: кольцо, стержень и три зубца. Цвет — currentColor. */
export function LogoMark({ className = "" }: LogoMarkProps) {
  return (
    <svg viewBox="0 0 260 532" className={className} fill="currentColor" aria-hidden>
      <path
        fillRule="evenodd"
        d="M107 0a107 107 0 1 1 0 214a107 107 0 1 1 0-214zm0 50a57 57 0 1 0 0 114a57 57 0 1 0 0-114z"
      />
      <rect x="82.5" y="180" width="49" height="351" rx="24.5" />
      <rect x="82.5" y="297" width="169.5" height="48" rx="24" />
      <rect x="82.5" y="391" width="130.5" height="48" rx="24" />
      <rect x="82.5" y="482" width="169.5" height="49" rx="24.5" />
    </svg>
  );
}

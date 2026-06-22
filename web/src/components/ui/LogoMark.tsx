interface LogoMarkProps {
  /** Lift the top-right shackle cap (unlocked state). */
  open?: boolean;
  className?: string;
}

/**
 * UnLock brand mark: a capsule padlock built from two U's (shackle arch + body)
 * with a bold U nested inside. Uses currentColor, so it inherits text colour.
 * Parts carry classes (lk-outer / lk-cap / lk-u) so callers can animate the cap.
 */
export function LogoMark({ open = false, className = "" }: LogoMarkProps) {
  return (
    <svg viewBox="0 0 100 132" className={className} fill="none" aria-hidden>
      <path
        className="lk-outer"
        d="M50 10 A26 26 0 0 0 24 36 L24 96 A26 26 0 0 0 76 96 L76 36"
        stroke="currentColor"
        strokeWidth={13}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        className="lk-cap"
        d="M76 36 A26 26 0 0 0 50 10"
        stroke="currentColor"
        strokeWidth={13}
        strokeLinecap="round"
        style={
          open
            ? { transformBox: "view-box", transformOrigin: "76px 36px", transform: "translate(6px,-10px) rotate(12deg)" }
            : undefined
        }
      />
      <path
        className="lk-u"
        d="M38 60 L38 82 A12 12 0 0 0 62 82 L62 60"
        stroke="currentColor"
        strokeWidth={12}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

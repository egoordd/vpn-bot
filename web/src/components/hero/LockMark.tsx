import "./lock.css";

/**
 * Brand centerpiece: a padlock that unlocks on a loop — the "UnLock" moment.
 * Pure SVG + CSS animation (no JS). The shackle clicks, swings open, holds,
 * then re-locks; a ring pulses outward at the instant it opens.
 */
export function LockMark() {
  return (
    <div className="lockmark" aria-hidden>
      <div className="lockmark__glow" />
      <svg viewBox="0 0 220 260" className="lockmark__svg" role="img" aria-label="Замок открывается">
        <circle className="lockmark__ring" cx="110" cy="178" r="86" />
        <circle className="lockmark__ring lockmark__ring--2" cx="110" cy="178" r="86" />

        <g className="lockmark__shackle">
          <path
            d="M 78 134 L 78 98 A 32 32 0 0 1 142 98 L 142 134"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="16"
            strokeLinecap="round"
          />
        </g>

        <rect className="lockmark__body" x="46" y="120" width="128" height="118" rx="28" />
        <circle className="lockmark__keyhole" cx="110" cy="168" r="11" />
        <path className="lockmark__keyhole" d="M 104 174 L 116 174 L 120 200 L 100 200 Z" />
      </svg>
    </div>
  );
}

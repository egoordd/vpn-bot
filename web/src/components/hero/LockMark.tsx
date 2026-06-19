import "./lock.css";

/**
 * Brand centerpiece: a dimensional (faux-3D) padlock that unlocks once on
 * entry. Metal shading comes from gradients driven by --lock-* tokens, so it
 * inverts with the theme (dark graphite on light, bright silver on dark).
 * Pure SVG + CSS — the shackle clicks, swings open and stays open.
 */
export function LockMark() {
  return (
    <div className="lockmark" aria-hidden>
      <svg viewBox="0 0 240 300" className="lockmark__svg" role="img" aria-label="Замок открывается">
        <defs>
          <linearGradient id="lockFace" x1="0" y1="0" x2="0.25" y2="1">
            <stop offset="0" stopColor="var(--lock-hi)" />
            <stop offset="0.5" stopColor="var(--lock-mid)" />
            <stop offset="1" stopColor="var(--lock-lo)" />
          </linearGradient>
          <linearGradient id="shackleGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="var(--lock-lo)" />
            <stop offset="0.32" stopColor="var(--lock-hi)" />
            <stop offset="0.6" stopColor="var(--lock-mid)" />
            <stop offset="1" stopColor="var(--lock-edge)" />
          </linearGradient>
          <linearGradient id="lockSheen" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="oklch(100% 0 0 / 0.22)" />
            <stop offset="1" stopColor="oklch(100% 0 0 / 0)" />
          </linearGradient>
          <radialGradient id="lockKey" cx="0.5" cy="0.4" r="0.7">
            <stop offset="0" stopColor="var(--lock-key)" />
            <stop offset="1" stopColor="var(--lock-key)" />
          </radialGradient>
        </defs>

        <ellipse className="lockmark__floor" cx="116" cy="280" rx="82" ry="13" />

        <g className="lockmark__shackle">
          <path
            d="M 84 142 L 84 104 A 32 32 0 0 1 148 104 L 148 142"
            fill="none"
            stroke="url(#shackleGrad)"
            strokeWidth="19"
            strokeLinecap="round"
          />
        </g>

        <rect className="lockmark__edge" x="58" y="134" width="128" height="120" rx="28" />
        <rect className="lockmark__body" x="52" y="128" width="128" height="120" rx="28" fill="url(#lockFace)" />
        <rect x="52" y="128" width="128" height="64" rx="28" fill="url(#lockSheen)" />

        <circle cx="116" cy="180" r="12" fill="url(#lockKey)" />
        <path d="M110 186 L122 186 L126 216 L106 216 Z" fill="url(#lockKey)" />
      </svg>
    </div>
  );
}

import "./connection-orbit.css";

/**
 * Hero centerpiece: a monochrome "connection field". A breathing aperture core
 * (the secure gateway) sits inside two tilted orbits that carry location nodes,
 * while a data pulse flows along a link into the core. Pure SVG + CSS — every
 * colour comes from theme tokens, so it inverts with the light/dark theme.
 * All motion is transform/opacity only and freezes under prefers-reduced-motion.
 */
export function ConnectionOrbit() {
  return (
    <div className="orbit" aria-hidden>
      <svg
        viewBox="0 0 440 440"
        className="orbit__svg"
        role="img"
        aria-label="Глобальная защищённая сеть"
      >
        <defs>
          <radialGradient id="orbitCore" cx="50%" cy="38%" r="65%">
            <stop offset="0" stopColor="var(--accent-2)" />
            <stop offset="1" stopColor="var(--accent-strong)" />
          </radialGradient>
          <radialGradient id="orbitHalo" cx="50%" cy="50%" r="50%">
            <stop offset="0" stopColor="var(--glow-accent)" />
            <stop offset="1" stopColor="transparent" />
          </radialGradient>
        </defs>

        <circle className="orbit__halo" cx="220" cy="216" r="206" fill="url(#orbitHalo)" />

        <g className="orbit__ring orbit__ring--a">
          <g transform="rotate(-20 220 216)">
            <ellipse cx="220" cy="216" rx="184" ry="66" className="orbit__path" />
            <circle cx="36" cy="216" r="7" className="orbit__node" />
            <circle cx="404" cy="216" r="4.5" className="orbit__node orbit__node--dim" />
          </g>
        </g>

        <g className="orbit__ring orbit__ring--b">
          <g transform="rotate(26 220 216)">
            <ellipse cx="220" cy="216" rx="72" ry="176" className="orbit__path" />
            <circle cx="220" cy="40" r="6" className="orbit__node" />
            <circle cx="220" cy="392" r="4" className="orbit__node orbit__node--dim" />
          </g>
        </g>

        <path className="orbit__link" d="M 64 250 Q 150 150 214 206" fill="none" />

        <g className="orbit__core">
          <circle cx="220" cy="216" r="58" className="orbit__core-halo" fill="url(#orbitHalo)" />
          <circle cx="220" cy="216" r="32" className="orbit__core-disc" fill="url(#orbitCore)" />
          <circle cx="220" cy="216" r="32" className="orbit__core-ring" fill="none" />
          <circle cx="220" cy="216" r="8.5" className="orbit__core-dot" />
        </g>
      </svg>
    </div>
  );
}

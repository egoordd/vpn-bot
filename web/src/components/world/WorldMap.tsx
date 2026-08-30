import { LIVE_LOCATIONS, SOON_LOCATIONS } from "@/lib/locations";

import "./world.css";

// Equirectangular dot-grid world (42×21). Land cells are rendered as dim pearl
// dots; the live VPN locations glow and pulse. Coarse on purpose — reads as a
// designed constellation, not a literal atlas.
const COLS = 42;
const ROWS = 21;
const GAP = 16;
const PAD = 8;
const DOT = 1.7;
const W = COLS * GAP;
const H = ROWS * GAP;

// Land segments per row: [colStart, colEnd] inclusive.
const LAND_ROWS: ReadonlyArray<ReadonlyArray<[number, number]>> = [
  [[8, 12], [16, 18], [26, 38]],
  [[3, 4], [5, 12], [16, 19], [20, 22], [24, 39]],
  [[3, 13], [16, 18], [20, 23], [24, 40]],
  [[4, 14], [20, 24], [25, 40]],
  [[5, 14], [20, 24], [25, 40]],
  [[6, 14], [20, 24], [26, 40]],
  [[6, 14], [21, 23], [26, 40]],
  [[7, 13], [21, 27], [28, 39]],
  [[9, 12], [21, 27], [28, 33], [34, 38]],
  [[11, 13], [21, 28], [30, 33], [34, 38]],
  [[12, 14], [22, 28], [31, 33], [35, 38]],
  [[13, 17], [23, 28], [35, 39]],
  [[13, 18], [23, 28], [35, 39]],
  [[13, 19], [24, 28], [36, 40]],
  [[13, 18], [24, 28], [36, 41]],
  [[14, 18], [24, 27], [36, 41]],
  [[14, 17], [25, 27], [37, 41]],
  [[14, 16], [25, 26], [38, 40]],
  [[14, 15], [26, 26]],
  [[14, 14]],
  [],
];

// Placement, names and status all come from the shared location list, so a
// server that goes live is added in exactly one place.
const LIVE = LIVE_LOCATIONS;
const SOON = SOON_LOCATIONS;

const cx = (col: number) => col * GAP + PAD;
const cy = (row: number) => row * GAP + PAD;

const byId = (id: string) => {
  const found = LIVE_LOCATIONS.find((n) => n.id === id);
  if (!found) throw new Error(`WorldMap: no live location "${id}" to anchor the arc`);
  return found;
};
const us = byId("us");
const nl = byId("nl");
const ARC = `M ${cx(us.col)} ${cy(us.row)} Q ${(cx(us.col) + cx(nl.col)) / 2} ${Math.min(cy(us.row), cy(nl.row)) - 64} ${cx(nl.col)} ${cy(nl.row)}`;

export function WorldMap() {
  const dots: Array<{ x: number; y: number }> = [];
  LAND_ROWS.forEach((segs, r) => {
    segs.forEach(([a, b]) => {
      for (let c = a; c <= b; c++) dots.push({ x: cx(c), y: cy(r) });
    });
  });

  return (
    <div className="wmap reveal">
      <div className="wmap__halo" aria-hidden />
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="wmap__svg"
        role="img"
        aria-label={`Карта мира: активные локации UnLock — ${LIVE.map((n) => n.name).join(", ")}; скоро — ${SOON.map((n) => n.name).join(", ")}`}
      >
        <g className="wmap__land">
          {dots.map((d, i) => (
            <circle key={i} cx={d.x} cy={d.y} r={DOT} />
          ))}
        </g>

        <path className="wmap__arc" d={ARC} />
        <circle className="wmap__packet" r="2.6">
          <animateMotion dur="3.4s" repeatCount="indefinite" path={ARC} calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" />
        </circle>

        {SOON.map((n) => (
          <circle key={n.id} className="wmap__soon" cx={cx(n.col)} cy={cy(n.row)} r="3.2" />
        ))}

        {LIVE.map((n) => (
          <g key={n.id} className="wmap__node">
            <circle className="wmap__pulse" cx={cx(n.col)} cy={cy(n.row)} r="4" />
            <circle className="wmap__pulse wmap__pulse--2" cx={cx(n.col)} cy={cy(n.row)} r="4" />
            <circle className="wmap__core" cx={cx(n.col)} cy={cy(n.row)} r="3.4" />
          </g>
        ))}
      </svg>

      <div className="wmap__labels" aria-hidden>
        {LIVE.map((n) => (
          <span
            key={n.id}
            className={n.labelBelow ? "wmap__label wmap__label--below" : "wmap__label"}
            style={{ left: `${(cx(n.col) / W) * 100}%`, top: `${(cy(n.row) / H) * 100}%` }}
          >
            <span className="wmap__label-flag">{n.flag}</span>
            {n.name}
          </span>
        ))}
      </div>
    </div>
  );
}

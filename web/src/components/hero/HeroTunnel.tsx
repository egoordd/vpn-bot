import "./hero-tunnel.css";

/**
 * Decorative "secure tunnel" — concentric rings + a packet travelling through.
 * Pure CSS/SVG, compositor-friendly (transform/opacity only). Hidden from AT.
 */
export function HeroTunnel() {
  const rings = [0, 1, 2, 3, 4, 5];
  return (
    <div className="tunnel" aria-hidden>
      <div className="tunnel__rings">
        {rings.map((i) => (
          <span key={i} className="tunnel__ring" style={{ ["--i" as string]: i }} />
        ))}
      </div>
      <span className="tunnel__packet" />
      <div className="tunnel__grid" />
    </div>
  );
}

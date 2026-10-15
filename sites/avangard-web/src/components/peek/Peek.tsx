"use client";

import { useEffect, useRef } from "react";

import { KEYHOLE_PATH } from "../ui/Tower";
import "./peek.css";

/* Скважина в листе: 33 × 84 с центром (64.5, 104). В завесе 1000 × 1000 — по центру, высотой ~100. */
const KEYHOLE_SCALE = 1.2;
const KEYHOLE_SHIFT = `translate(${500 - 64.5 * KEYHOLE_SCALE} ${500 - 104 * KEYHOLE_SCALE}) scale(${KEYHOLE_SCALE})`;
const MAX_ZOOM = 80;

const CHIPS = ["Шифрование TLS 1.3", "Выходы в Германии и Нидерландах", "До 5 устройств"] as const;

/* «Загляните внутрь»: тёмная завеса со скважиной; при прокрутке скважина растёт и открывает светлый двор. */
export function Peek() {
  const section = useRef<HTMLElement>(null);
  const veil = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const root = section.current;
    const cover = veil.current;
    if (!root || !cover || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      root?.classList.add("is-static");
      return;
    }
    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = root.getBoundingClientRect();
      const travel = rect.height - window.innerHeight;
      const progress = Math.min(1, Math.max(0, -rect.top / Math.max(travel, 1)));
      const zoom = 1 + MAX_ZOOM * progress ** 2.4;
      cover.style.transform = `scale(${zoom})`;
      cover.style.visibility = progress > 0.96 ? "hidden" : "visible";
      root.style.setProperty("--p", progress.toFixed(3));
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <section ref={section} className="peek" aria-labelledby="peek-title">
      <div className="peek__sticky">
        <div className="peek__inside">
          <span className="eyebrow">Внутри крепости</span>
          <h2 id="peek-title">Здесь только вы</h2>
          <p>
            Шифрование закрывает соединение, как ворота замка: ни владелец Wi-Fi в кафе, ни провайдер не видят,
            какие сайты вы открываете и что пишете.
          </p>
          <ul className="peek__chips">
            {CHIPS.map((chip) => (
              <li key={chip}>{chip}</li>
            ))}
          </ul>
        </div>
        <svg ref={veil} className="peek__veil" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          <defs>
            <mask id="peek-hole">
              <rect width="1000" height="1000" fill="#fff" />
              <path d={KEYHOLE_PATH} transform={KEYHOLE_SHIFT} fill="#000" />
            </mask>
          </defs>
          <rect width="1000" height="1000" fill="#0B231B" mask="url(#peek-hole)" />
          <path d={KEYHOLE_PATH} transform={KEYHOLE_SHIFT} fill="none" stroke="#B08A3E" strokeWidth="1.2" />
        </svg>
        <p className="peek__hint" aria-hidden="true">
          Загляните внутрь
        </p>
      </div>
    </section>
  );
}

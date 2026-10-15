"use client";

import { useEffect, useRef } from "react";

import { KEYHOLE_PATH } from "../ui/Tower";
import "./peek.css";

/* Скважина в листе: 33 × 84 с центром (64.5, 104). В завесе 1000 × 1000 — по центру, высотой ~100. */
const KEYHOLE_SCALE = 1.2;
const KEYHOLE_SHIFT = `translate(${500 - 64.5 * KEYHOLE_SCALE} ${500 - 104 * KEYHOLE_SCALE}) scale(${KEYHOLE_SCALE})`;

const CHIPS = ["Шифрование TLS 1.3", "Выходы в Германии и Нидерландах", "До 5 устройств"] as const;

/**
 * «Загляните внутрь»: тёмная завеса со скважиной. Когда блок на экране, скважина один раз раскрывается
 * CSS-анимацией и открывает светлый двор. 15.10.2026: раньше масштаб считался от прокрутки (до 80×) —
 * на быстрой прокрутке, особенно на телефоне, сцена отставала и мерцала; теперь прокрутка её не трогает.
 */
export function Peek() {
  const section = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = section.current;
    if (!root) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      root.classList.add("is-open", "is-static");
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          root.classList.add("is-open");
          observer.disconnect();
        }
      },
      { threshold: 0.55 },
    );
    observer.observe(root);
    return () => observer.disconnect();
  }, []);

  return (
    <section ref={section} className="peek" aria-labelledby="peek-title">
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
      <svg className="peek__veil" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
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
    </section>
  );
}

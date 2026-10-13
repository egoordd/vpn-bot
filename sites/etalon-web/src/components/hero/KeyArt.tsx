"use client";

import { useEffect, useRef } from "react";

/** Объёмный золотой ключ-«E»: металлический градиент, блик и тень; чуть поворачивается за курсором. */
export function KeyArt() {
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const onMove = (event: PointerEvent) => {
      const rect = stage.getBoundingClientRect();
      const x = (event.clientX - (rect.left + rect.width / 2)) / rect.width;
      const y = (event.clientY - (rect.top + rect.height / 2)) / rect.height;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        stage.style.setProperty("--ry", `${Math.max(-1, Math.min(1, x)) * 10}deg`);
        stage.style.setProperty("--rx", `${Math.max(-1, Math.min(1, y)) * -8}deg`);
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  return (
    <div className="keyart" ref={stageRef} aria-hidden>
      <div className="keyart__orb" />
      <div className="keyart__ring keyart__ring--1" />
      <div className="keyart__ring keyart__ring--2" />
      <div className="keyart__float">
        <svg className="keyart__key" viewBox="-10 -10 280 552">
          <defs>
            <linearGradient id="kg-body" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#7C5B22" />
              <stop offset="0.16" stopColor="#C9A45C" />
              <stop offset="0.33" stopColor="#F5E6BA" />
              <stop offset="0.48" stopColor="#D5B26C" />
              <stop offset="0.66" stopColor="#9F7B37" />
              <stop offset="0.84" stopColor="#E9D3A0" />
              <stop offset="1" stopColor="#8A682B" />
            </linearGradient>
            <linearGradient id="kg-edge" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#FFF6DC" stopOpacity="0.9" />
              <stop offset="1" stopColor="#FFF6DC" stopOpacity="0" />
            </linearGradient>
            <radialGradient id="kg-shine" cx="0.3" cy="0.12" r="0.55">
              <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.75" />
              <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
            </radialGradient>
            <clipPath id="kg-shape">
              <path d="M107 0a107 107 0 1 1 0 214a107 107 0 1 1 0-214zm0 50a57 57 0 1 0 0 114a57 57 0 1 0 0-114z" fillRule="evenodd" clipRule="evenodd" />
              <rect x="82.5" y="180" width="49" height="351" rx="24.5" />
              <rect x="82.5" y="297" width="169.5" height="48" rx="24" />
              <rect x="82.5" y="391" width="130.5" height="48" rx="24" />
              <rect x="82.5" y="482" width="169.5" height="49" rx="24.5" />
            </clipPath>
          </defs>
          <g clipPath="url(#kg-shape)">
            <rect x="-10" y="-10" width="280" height="552" fill="url(#kg-body)" />
            <rect x="-10" y="-10" width="280" height="552" fill="url(#kg-shine)" />
          </g>
          <path
            d="M107 3a104 104 0 0 1 104 104"
            fill="none"
            stroke="url(#kg-edge)"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <path d="M85 200v300" stroke="#FFF6DC" strokeOpacity="0.45" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
        <div className="keyart__shadow" />
      </div>
    </div>
  );
}

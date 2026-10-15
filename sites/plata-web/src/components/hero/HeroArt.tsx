"use client";

import { useEffect, useState } from "react";

import { ShieldMark } from "../ui/ShieldMark";

const START_SECONDS = 12 * 60 + 48;

function clock(seconds: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds / 60) % 60)}:${pad(seconds % 60)}`;
}

/* Щит и «окна приложения» вокруг: защита включена (идёт время сеанса), Госуслуги напрямую, 5 устройств. */
export function HeroArt() {
  const [seconds, setSeconds] = useState(START_SECONDS);

  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="art" aria-hidden="true">
      <div className="art__glow" />
      <div className="art__ring art__ring--1" />
      <div className="art__ring art__ring--2" />
      <ShieldMark className="art__shield" />

      <div className="art__card art__card--status">
        <span className="art__label">
          <i className="art__live" /> Защита включена
        </span>
        <strong className="art__clock">{clock(seconds)}</strong>
        <span className="art__route">⚡️ Авто · 🇫🇮 Финляндия</span>
      </div>

      <div className="art__card art__card--ru">
        <span className="art__check">✓</span>
        <span>
          <b>Госуслуги и банки</b>
          <em>открываются напрямую</em>
        </span>
      </div>

      <div className="art__card art__card--devices">
        <span className="art__devices">📱 💻 🖥</span>
        <b>до 5 устройств</b>
      </div>
    </div>
  );
}

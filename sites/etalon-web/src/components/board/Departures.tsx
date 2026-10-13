"use client";

import { useEffect, useRef } from "react";

import "./board.css";

interface Route {
  flag: string;
  city: string;
  code: string;
  flight: string;
  time: string;
  status: string;
  boarding?: boolean;
}

const ROUTES: Route[] = [
  { flag: "⚡️", city: "АВТОПИЛОТ", code: "AUTO", flight: "ETL 777", time: "ЛУЧШИЙ", status: "ВЫБИРАЕТ САМ", boarding: true },
  { flag: "🇳🇱", city: "НИДЕРЛАНДЫ", code: "NLD", flight: "ETL 201", time: "≈38 МС", status: "ПОСАДКА", boarding: true },
  { flag: "🇫🇮", city: "ФИНЛЯНДИЯ", code: "FIN", flight: "ETL 358", time: "≈36 МС", status: "ПО РАСПИСАНИЮ" },
  { flag: "🇵🇱", city: "ПОЛЬША", code: "POL", flight: "ETL 048", time: "≈45 МС", status: "ПО РАСПИСАНИЮ" },
  { flag: "🇺🇸", city: "США", code: "USA", flight: "ETL 001", time: "≈110 МС", status: "ПО РАСПИСАНИЮ" },
];

const GLYPHS = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЭЮЯ0123456789";

/** Буквы ячейки перещёлкиваются, как на табло, и останавливаются на своём значении. */
function Flap({ text }: { text: string }) {
  return (
    <span className="flap" aria-hidden>
      {Array.from(text).map((ch, i) => (
        <span key={i} className="flap__cell" data-final={ch}>
          {ch}
        </span>
      ))}
    </span>
  );
}

export function Departures() {
  const boardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const board = boardRef.current;
    if (!board || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const cells = Array.from(board.querySelectorAll<HTMLElement>(".flap__cell"));
    const timers: number[] = [];

    const run = () => {
      cells.forEach((cell, i) => {
        const final = cell.dataset.final ?? "";
        if (final === " ") return;
        let ticks = 6 + ((i * 7) % 11);
        const timer = window.setInterval(() => {
          ticks -= 1;
          if (ticks <= 0) {
            cell.textContent = final;
            cell.classList.remove("is-flipping");
            window.clearInterval(timer);
            return;
          }
          cell.textContent = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
          cell.classList.add("is-flipping");
        }, 55);
        timers.push(timer);
      });
    };

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          run();
          observer.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(board);
    return () => {
      observer.disconnect();
      timers.forEach((t) => window.clearInterval(t));
    };
  }, []);

  return (
    <section id="routes" className="section routes" aria-labelledby="routes-title">
      <div className="container">
        <header className="section-head reveal">
          <span className="eyebrow">Табло вылетов</span>
          <h2 id="routes-title">Четыре направления и автопилот</h2>
          <p className="lead">
            Европа и США в одной подписке. Нужна конкретная страна — выберите её. Не хотите выбирать — автопилот
            сам держит самое быстрое направление.
          </p>
        </header>

        <div className="board reveal" ref={boardRef} role="table" aria-label="Направления Etalon VPN">
          <div className="board__head" role="row">
            <span role="columnheader">Направление</span>
            <span role="columnheader">Рейс</span>
            <span role="columnheader">В пути</span>
            <span role="columnheader">Статус</span>
          </div>
          {ROUTES.map((r) => (
            <div key={r.code} className={`board__row${r.boarding ? " is-boarding" : ""}`} role="row">
              <span role="cell" className="board__dest">
                <span className="board__flag">{r.flag}</span>
                <Flap text={r.city} />
                <span className="sr">{`${r.city}, `}</span>
              </span>
              <span role="cell">
                <Flap text={r.flight} />
                <span className="sr">{r.flight}</span>
              </span>
              <span role="cell">
                <Flap text={r.time} />
                <span className="sr">{r.time}</span>
              </span>
              <span role="cell" className="board__status">
                <Flap text={r.status} />
                <span className="sr">{r.status}</span>
              </span>
            </div>
          ))}
        </div>
        <p className="routes__note reveal">
          «В пути» — примерный отклик сервера из Москвы. Все направления входят в любой тариф.
        </p>
      </div>
    </section>
  );
}

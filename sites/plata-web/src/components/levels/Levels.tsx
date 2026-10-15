"use client";

import { useEffect, useRef, useState } from "react";

import { ShieldMark } from "../ui/ShieldMark";
import "./levels.css";

const LEVELS = [
  {
    title: "Шифрование",
    text: "Весь трафик идёт по зашифрованному каналу — дома, в кафе, в аэропорту. Пароли и переписку не перехватить в чужой сети Wi-Fi.",
    note: "Протокол VLESS Reality",
  },
  {
    title: "Самый быстрый сервер",
    text: "Приложение само выбирает сервер с лучшей скоростью и переключается, если какой-то из них замедлился. Ничего настраивать не нужно.",
    note: "Польша · Финляндия · Нидерланды · США",
  },
  {
    title: "Российские сервисы напрямую",
    text: "Банки, Госуслуги и маркетплейсы открываются как обычно — VPN не нужно выключать каждый раз, чтобы оплатить или войти.",
    note: "Режим РУ-сервисов",
  },
  {
    title: "Одна подписка — пять устройств",
    text: "Телефон, планшет, ноутбук и компьютер под одной подпиской. iPhone, iPad, Android, Windows и Mac.",
    note: "Приложение Happ",
  },
] as const;

/* «Четыре уровня защиты»: щит слева стоит на месте, шевроны зажигаются по мере прокрутки. */
export function Levels() {
  const [lit, setLit] = useState(1);
  const items = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setLit(Number((entry.target as HTMLElement).dataset.level));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    items.current.forEach((item) => item && observer.observe(item));
    return () => observer.disconnect();
  }, []);

  return (
    <section className="section levels" id="levels" aria-labelledby="levels-title">
      <div className="wrap">
        <div className="section-head">
          <span className="eyebrow">Защита</span>
          <h2 id="levels-title">Четыре уровня защиты в одной подписке</h2>
          <p>Как шевроны на щите: каждый уровень добавляет надёжности, а вместе они работают сами — без настроек.</p>
        </div>
        <div className="levels__grid">
          <div className="levels__stage" aria-hidden="true">
            <div className="levels__badge">
              <ShieldMark className="levels__shield" chevrons={4} lit={lit} />
              <span className="levels__count">
                Уровень <b>{lit}</b> из 4
              </span>
            </div>
          </div>
          <ol className="levels__list">
            {LEVELS.map((level, index) => (
              <li
                key={level.title}
                ref={(node) => {
                  items.current[index] = node;
                }}
                data-level={index + 1}
                className={`level${index + 1 <= lit ? " is-lit" : ""}`}
              >
                <ShieldMark className="level__mini" chevrons={4} lit={index + 1} />
                <span className="level__num">0{index + 1}</span>
                <h3>{level.title}</h3>
                <p>{level.text}</p>
                <span className="level__note">{level.note}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

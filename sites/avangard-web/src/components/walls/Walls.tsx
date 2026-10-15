import type { ReactNode } from "react";

import { LANGUAGES } from "@/lib/site";
import "./walls.css";

const ICONS: Record<string, ReactNode> = {
  lock: <path d="M7 11V8a5 5 0 0 1 10 0v3M5.5 11h13v9.5h-13zM12 14.5v2.5" />,
  auto: <path d="M4 12a8 8 0 0 1 13.7-5.6M20 12a8 8 0 0 1-13.7 5.6M17.7 3v3.4h-3.4M6.3 21v-3.4h3.4" />,
  bridge: <path d="M2 18h20M4 18v-4a8 8 0 0 1 16 0v4M8 18v-3M12 18v-4M16 18v-3" />,
  devices: <path d="M3 6.5h12v9H3zM1.5 18h15M18 8.5h4v11h-4zM20 17.5h0" />,
  globe: <path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.6 3.6 5.6 3.6 9s-1.1 6.4-3.6 9c-2.5-2.6-3.6-5.6-3.6-9S9.5 5.6 12 3z" />,
};

const STONES = [
  {
    icon: "lock",
    title: "Шифрование",
    text: "Соединение закрыто от чужих глаз — дома, в кафе, в аэропорту. Пароли и переписку не перехватить в чужой сети Wi-Fi.",
  },
  {
    icon: "auto",
    title: "Авто-выбор",
    text: "Приложение само держит самый быстрый из серверов и переключается, если какой-то замедлился. Ничего настраивать не нужно.",
  },
  {
    icon: "bridge",
    title: "Надёжный вход",
    text: "Подключение идёт через мост — скорость остаётся ровной даже на домашнем интернете.",
  },
  {
    icon: "devices",
    title: "Пять устройств",
    text: "Телефон, планшет и компьютер под одной подпиской: iPhone, Android, Windows и Mac.",
  },
  {
    icon: "globe",
    title: "Пять языков",
    text: LANGUAGES.map((lang) => `${lang.flag} ${lang.name}`).join("  ·  "),
  },
] as const;

export function Walls() {
  return (
    <section className="section walls" id="walls" aria-labelledby="walls-title">
      <div className="wrap">
        <div className="section-head">
          <span className="eyebrow">Стены</span>
          <h2 id="walls-title">Из чего сложена защита</h2>
          <p>Пять камней в основании крепости — все работают сами, с первой минуты.</p>
        </div>
        <ul className="stones">
          {STONES.map((stone) => (
            <li key={stone.title} className="stone">
              <svg className="stone__icon" viewBox="0 0 24 24" aria-hidden="true">
                {ICONS[stone.icon]}
              </svg>
              <h3>{stone.title}</h3>
              <p>{stone.text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

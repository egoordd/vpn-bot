import { useId } from "react";

interface ShieldMarkProps {
  className?: string;
  /** Сколько шевронов внутри щита: знак — один, в разделе «Уровни защиты» — четыре. */
  chevrons?: 1 | 4;
  /** Сколько из них подсвечено янтарём (снизу вверх), остальные приглушены. */
  lit?: number;
  title?: string;
}

const SHIELD = "M32 2 58 11v22c0 18-11 31-26 37C17 64 6 51 6 33V11Z";
/* Вершины шевронов (x всегда 32): один — как на логотипе, четыре — «погоны» снизу вверх. */
const LAYOUTS = {
  1: { apexes: [26], half: 17, drop: 15, width: 8 },
  4: { apexes: [14, 26, 38, 50], half: 13, drop: 9, width: 5.5 },
} as const;

/* Щит с янтарным шевроном — как на логотипе заказчика. */
export function ShieldMark({ className, chevrons = 1, lit = chevrons, title }: ShieldMarkProps) {
  // useId даёт id с двоеточиями и «ёлочками» — они ломают ссылку url(#…) на градиент внутри SVG.
  const gradient = `amber${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const { apexes, half, drop, width } = LAYOUTS[chevrons];
  return (
    <svg className={className} viewBox="0 0 64 72" role={title ? "img" : undefined} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#F7C866" />
          <stop offset="1" stopColor="#F2A448" />
        </linearGradient>
      </defs>
      <path d={SHIELD} fill="#172854" />
      {apexes.map((apex, index) => {
        const on = apexes.length - index <= lit;
        return (
          <path
            key={apex}
            className="shield-chevron"
            data-on={on}
            d={`M${32 - half} ${apex + drop} 32 ${apex} ${32 + half} ${apex + drop}`}
            fill="none"
            stroke={on ? `url(#${gradient})` : "rgb(255 255 255 / 0.13)"}
            strokeWidth={width}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        );
      })}
    </svg>
  );
}

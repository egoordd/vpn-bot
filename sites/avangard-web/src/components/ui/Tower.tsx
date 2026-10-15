/* Знак «Замок»: башня с тремя зубцами и замочной скважиной (пропорции фирменного листа, 129 × 176).
   Скважина — сквозной вырез (evenodd): сквозь неё видно то, что лежит за башней. Цвет — currentColor. */
export const TOWER_PATH =
  "M0 13A13 13 0 0 1 26 13V26H51.5V13A13 13 0 0 1 77.5 13V26H103V13A13 13 0 0 1 129 13V162A14 14 0 0 1 115 176H14A14 14 0 0 1 0 162Z" +
  "M52.6 91A17 17 0 1 1 76.4 91L81 142Q81 146 77 146H52Q48 146 48 142Z";

/* Только скважина — для маски «заглянуть внутрь». Центр круга — (64.5, 79). */
export const KEYHOLE_PATH = "M52.6 91A17 17 0 1 1 76.4 91L81 142Q81 146 77 146H52Q48 146 48 142Z";

interface TowerProps {
  className?: string;
  title?: string;
}

export function Tower({ className, title }: TowerProps) {
  return (
    <svg className={className} viewBox="0 0 129 176" role={title ? "img" : undefined} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      <path d={TOWER_PATH} fill="currentColor" fillRule="evenodd" />
    </svg>
  );
}

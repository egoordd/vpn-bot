/**
 * Страны Etalon VPN — те же четыре, что в подписке бота (Польша, Финляндия,
 * Нидерланды, США). Всё, что называет или считает страны, читает отсюда.
 *
 * Grid coordinates are the world map's 42×21 equirectangular-ish placement and
 * are ignored everywhere else.
 */
export interface VpnLocation {
  id: string;
  flag: string;
  name: string;
  status: "live" | "soon";
  /** Shown beside the name in the location list. Live entries only. */
  note?: string;
  col: number;
  row: number;
  labelBelow?: boolean;
}

export const LOCATIONS: readonly VpnLocation[] = [
  { id: "us", flag: "🇺🇸", name: "США", status: "live", note: "стабильно и быстро", col: 12, row: 6 },
  { id: "nl", flag: "🇳🇱", name: "Нидерланды", status: "live", note: "самый быстрый в Европе", col: 22, row: 4 },
  { id: "fi", flag: "🇫🇮", name: "Финляндия", status: "live", note: "стабильно и быстро", col: 25, row: 3 },
  { id: "pl", flag: "🇵🇱", name: "Польша", status: "live", note: "стабильно и быстро", col: 24, row: 5, labelBelow: true },
];

export const LIVE_LOCATIONS = LOCATIONS.filter((l) => l.status === "live");
export const SOON_LOCATIONS = LOCATIONS.filter((l) => l.status === "soon");

/** `4 страны`, `1 страна`, `5 стран` — Russian counting for the trust bar. */
export function pluralCountries(count: number): string {
  const tail = Math.abs(count) % 100;
  if (tail >= 11 && tail <= 14) return `${count} стран`;
  const last = tail % 10;
  if (last === 1) return `${count} страна`;
  if (last >= 2 && last <= 4) return `${count} страны`;
  return `${count} стран`;
}

export const LIVE_COUNTRIES_LABEL = pluralCountries(LIVE_LOCATIONS.length);

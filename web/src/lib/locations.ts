/**
 * The one list of places we sell.
 *
 * It used to live in three components at once — the world map, the location
 * list, and a hand-typed "2 страны" in the trust bar. The count drifted: we
 * were running four countries while the front page still advertised two.
 * Everything that names a location, or counts them, reads from here.
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
  { id: "nl", flag: "🇳🇱", name: "Нидерланды", status: "live", note: "стабильно и быстро", col: 22, row: 4 },
  { id: "lt", flag: "🇱🇹", name: "Литва", status: "live", note: "быстрая, без рекламы в YouTube", col: 25, row: 4 },
  { id: "pl", flag: "🇵🇱", name: "Польша", status: "live", note: "стабильно и быстро", col: 24, row: 5, labelBelow: true },
  { id: "de", flag: "🇩🇪", name: "Германия", status: "live", note: "самый быстрый", col: 22, row: 6, labelBelow: true },
  { id: "uk", flag: "🇬🇧", name: "Англия", status: "soon", col: 20, row: 4 },
  { id: "fi", flag: "🇫🇮", name: "Финляндия", status: "soon", col: 25, row: 3 },
  { id: "ny", flag: "🗽", name: "Нью-Йорк", status: "soon", col: 14, row: 6 },
  { id: "la", flag: "🌴", name: "Лос-Анджелес", status: "soon", col: 8, row: 7 },
  { id: "ae", flag: "🇦🇪", name: "ОАЭ", status: "soon", col: 27, row: 8 },
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

/**
 * Money helpers — mirror of the backend `services/money.py`.
 * Internal amounts are integer kopecks (RUB minor units); 1 RUB = 100 kopecks.
 */
export const KOPECKS_IN_RUB = 100;

export function kopecksToRubles(kopecks: number): number {
  return kopecks / KOPECKS_IN_RUB;
}

/** Human-readable rouble string, dropping a trailing `.00`. */
export function formatRub(kopecks: number): string {
  const rub = kopecksToRubles(kopecks);
  const isWhole = Number.isInteger(rub);
  const body = isWhole
    ? rub.toLocaleString("ru-RU")
    : rub.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${body} ₽`;
}

/** Whole roubles → display string (for catalogue prices). */
export function formatRubFromRubles(rubles: number): string {
  return `${rubles.toLocaleString("ru-RU")} ₽`;
}

export function percentOf(amountKopecks: number, percent: number): number {
  return Math.round((amountKopecks * percent) / 100);
}

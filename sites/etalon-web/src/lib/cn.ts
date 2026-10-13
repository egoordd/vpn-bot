type ClassValue = string | number | false | null | undefined;

/** Minimal classnames join — avoids a dependency for trivial composition. */
export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}

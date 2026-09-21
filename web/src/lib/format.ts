export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function fixed(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

/** D rows read as recall (more is better); N rows read as false alarms (less is better). */
export function metricTone(value: number, isDrift: boolean): "good" | "mid" | "bad" {
  const good = isDrift ? value >= 0.66 : value <= 0.1;
  const bad = isDrift ? value < 0.34 : value > 0.33;
  return good ? "good" : bad ? "bad" : "mid";
}

export const CATEGORY_ORDER = [
  "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "N1", "N2", "N3",
];

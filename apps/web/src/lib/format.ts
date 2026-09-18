import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const ZERO_DECIMAL = new Set(["UGX", "RWF", "JPY"]);

export function formatPrice(amountMinor: number, currency: string, locale?: string): string {
  const major = ZERO_DECIMAL.has(currency) ? amountMinor : amountMinor / 100;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: ZERO_DECIMAL.has(currency) ? 0 : 2,
  }).format(major);
}

export const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "n/a" : `${(v * 100).toFixed(digits)}%`;

export const odds = (v: number | null | undefined) => (v == null ? "n/a" : v.toFixed(2));

export const prob = (v: number | null | undefined) => (v == null ? "n/a" : v.toFixed(3));

/** Kick-off in the viewer's own time zone (stored in UTC). */
export function kickoff(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

export function pickLabel(pick: "home" | "draw" | "away" | null, home: string, away: string): string {
  if (pick === "home") return `${home} to win`;
  if (pick === "away") return `${away} to win`;
  if (pick === "draw") return "Draw";
  return "Locked";
}

export function isoDate(d = new Date()): string {
  return d.toISOString().slice(0, 10);
}

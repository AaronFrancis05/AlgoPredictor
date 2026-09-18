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

/** Kick-off time only ("19:30"), in the viewer's time zone. */
export function kickoffTime(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

/** The viewer's local calendar date (YYYY-MM-DD) of an instant. */
export function localDay(iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function initials(name: string, email: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  return (words[0]?.[0] ?? email[0] ?? "?").toUpperCase();
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

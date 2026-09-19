/**
 * Browser API client. Same-origin (/api/v1 is rewritten to FastAPI), cookies are httpOnly.
 * - Sends the CSRF double-submit header on writes.
 * - On 401 it refreshes the session once and retries.
 * - Every response is validated with its Zod schema; a mismatch is an error, not silent bad data.
 */
import type { z } from "zod";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
    message: string,
  ) {
    super(message);
  }

  get code(): string | undefined {
    const d = this.detail as { code?: string } | undefined;
    return typeof d === "object" && d ? d.code : undefined;
  }
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.split("=")[1];
}

/** ok: new session cookies are set. signed_out: the server refused the session. unavailable: no answer (network,
 * 5xx, 429), so the session may well still be good. */
export type RefreshOutcome = "ok" | "signed_out" | "unavailable";

async function attemptRefresh(): Promise<RefreshOutcome> {
  try {
    const r = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" });
    if (r.ok) return "ok";
    return r.status >= 500 || r.status === 429 ? "unavailable" : "signed_out";
  } catch {
    return "unavailable";
  }
}

const REFRESH_RETRY_MS = 1_000;

/** One refresh with a single retry when the server did not answer. The first request after a quiet spell is the
 * one most likely to hit a cold connection, and giving up there would sign the visitor out for nothing. */
export async function refreshWithRetry(
  attempt: () => Promise<RefreshOutcome> = attemptRefresh,
  wait: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<RefreshOutcome> {
  const first = await attempt();
  if (first !== "unavailable") return first;
  await wait(REFRESH_RETRY_MS);
  return attempt();
}

let refreshing: Promise<RefreshOutcome> | null = null;

function refreshSession(): Promise<RefreshOutcome> {
  refreshing ??= refreshWithRetry().finally(() => {
    setTimeout(() => (refreshing = null), 0);
  });
  return refreshing;
}

/** Drop the readable session marker once the server has refused the session (the API clears the httpOnly cookies
 * itself). Without this the public pages keep offering "Dashboard" to someone who is signed out. */
export function forgetSession(): void {
  if (typeof document !== "undefined") document.cookie = "ap_csrf=; Max-Age=0; path=/; SameSite=Lax";
}

function messageFrom(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ");
  if (detail && typeof detail === "object" && "code" in detail) {
    const code = (detail as { code: string }).code;
    const known: Record<string, string> = {
      upgrade_required: "This feature needs a higher plan.",
      email_not_verified: "Please confirm your email address first.",
      age_not_confirmed: "Please confirm you are 18 or older.",
      slip_quota: "You have used today's slip allowance.",
      verify_first: "Confirm your email and age before subscribing.",
      admin_full_access: "Admin accounts already have every feature. There is nothing to pay.",
      plan_already_covered:
        "Your current plan already includes everything this code gives, so it was not used. Keep it for later or pass it on.",
      mfa_invalid: "That code is not right. Codes change every 30 seconds; check your phone's clock and try again.",
      mfa_expired: "Sign-in timed out. Enter your password again.",
      mfa_locked: "Too many wrong codes. Try again in 15 minutes.",
      mfa_required: "Admin pages need two-factor sign-in. Turn it on under Account, Sign-in methods.",
      mfa_reauth: "Admin pages need a session started with your authenticator code. Sign out and sign in again.",
      mfa_already_enabled: "Two-factor sign-in is already on.",
    };
    return known[code] ?? code;
  }
  return status === 429 ? "Too many requests. Please slow down." : `Request failed (${status})`;
}

export async function api<S extends z.ZodTypeAny>(
  path: string,
  schema: S,
  init: RequestInit & { json?: unknown } = {},
  retried = false,
): Promise<z.infer<S>> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.json !== undefined) headers.set("content-type", "application/json");
  if (method !== "GET" && method !== "HEAD") {
    const csrf = readCookie("ap_csrf");
    if (csrf) headers.set("x-csrf-token", csrf);
  }
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
  if (res.status === 401 && !retried && !path.startsWith("/auth/")) {
    const outcome = await refreshSession();
    if (outcome === "ok") return api(path, schema, init, true);
    if (outcome === "unavailable") {
      // not a sign-out: report it as a server problem so the page offers a retry instead of the sign-in form
      throw new ApiError(503, null, "Could not reach the server. Check your connection and try again.");
    }
    forgetSession();
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    throw new ApiError(res.status, detail, messageFrom(detail, res.status));
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(500, parsed.error.issues, "Unexpected response from the server");
  }
  return parsed.data;
}

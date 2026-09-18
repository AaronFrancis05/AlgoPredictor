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

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" })
    .then((r) => r.ok)
    .finally(() => {
      setTimeout(() => (refreshing = null), 0);
    });
  return refreshing;
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
    if (await refreshSession()) return api(path, schema, init, true);
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

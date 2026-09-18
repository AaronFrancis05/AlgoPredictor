import "server-only";

import { cookies, headers } from "next/headers";
import type { z } from "zod";

import { visitorHeaders } from "@/lib/client-ip";

/**
 * Server-side fetch of PUBLIC API data (plans, track record, free picks) for SSR/SEO pages.
 * Uses Next's data cache with tags so the API can revalidate after each ingest (see /api/revalidate).
 * Returns null instead of throwing, so a public page still renders when the API is unavailable.
 */
const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export async function serverGet<S extends z.ZodTypeAny>(
  path: string,
  schema: S,
  opts: { revalidate?: number; tags?: string[] } = {},
): Promise<z.infer<S> | null> {
  try {
    const res = await fetch(`${API}/api/v1${path}`, {
      next: { revalidate: opts.revalidate ?? 300, tags: opts.tags ?? [] },
      headers: { accept: "application/json" },
    });
    if (!res.ok) return null;
    const parsed = schema.safeParse(await res.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

/** How long a signed-in page waits for the API before rendering without prefetched data (the browser then loads
 * it as before). Keeps a slow API from delaying the first byte. */
const SESSION_TIMEOUT_MS = 2500;

/**
 * Server-side fetch of the VISITOR'S OWN data during a page render, with their access cookie, so signed-in pages
 * arrive with data instead of a loading skeleton. Never cached. Returns null without a session, on any error, or
 * when the access token has expired (the browser then refreshes the session and fetches as usual).
 */
export async function sessionGet<S extends z.ZodTypeAny>(path: string, schema: S): Promise<z.infer<S> | null> {
  const access = (await cookies()).get("ap_access")?.value;
  if (!access) return null;
  const forwardedFor = (await headers()).get("x-forwarded-for");
  try {
    const res = await fetch(`${API}/api/v1${path}`, {
      cache: "no-store",
      headers: { accept: "application/json", cookie: `ap_access=${access}`, ...visitorHeaders(forwardedFor) },
      signal: AbortSignal.timeout(SESSION_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const parsed = schema.safeParse(await res.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

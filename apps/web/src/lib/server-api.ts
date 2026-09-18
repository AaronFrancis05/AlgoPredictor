import "server-only";

import type { z } from "zod";

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

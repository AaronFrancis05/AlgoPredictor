import { revalidateTag } from "next/cache";
import { NextResponse, type NextRequest } from "next/server";
import { timingSafeEqual } from "node:crypto";
import { z } from "zod";

/** Called by the API after each ingest so public pages show new picks/results without waiting for the TTL. */
const Body = z.object({ tags: z.array(z.enum(["picks", "track-record", "plans"])).min(1).max(5) });

function safeEqual(a: string, b: string) {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export async function POST(request: NextRequest) {
  const secret = process.env.REVALIDATE_SECRET ?? "";
  const given = request.headers.get("x-revalidate-secret") ?? "";
  if (!secret || !safeEqual(given, secret)) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }
  const parsed = Body.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ detail: "Invalid body" }, { status: 422 });
  for (const tag of parsed.data.tags) revalidateTag(tag, "max");
  return NextResponse.json({ revalidated: parsed.data.tags });
}

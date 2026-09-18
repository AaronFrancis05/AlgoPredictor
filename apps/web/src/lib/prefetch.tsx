import "server-only";

import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { z } from "zod";

import { sessionGet } from "@/lib/server-api";

type Prefetch = { key: readonly unknown[]; path: string; schema: z.ZodTypeAny };

/**
 * Fetches the visitor's data on the server (in parallel) and hands it to the browser's query cache, so the page
 * renders with data on the first paint. Anything that fails is simply left for the browser to load.
 */
export async function Prefetched({ queries, children }: { queries: Prefetch[]; children: ReactNode }) {
  const client = new QueryClient();
  const results = await Promise.all(queries.map((q) => sessionGet(q.path, q.schema)));
  queries.forEach((q, i) => {
    if (results[i] != null) client.setQueryData(q.key, results[i]);
  });
  return <HydrationBoundary state={dehydrate(client)}>{children}</HydrationBoundary>;
}

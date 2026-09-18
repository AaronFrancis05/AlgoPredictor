/** Query definitions shared by client components and the server-side prefetch (same keys on both sides). */
import { api } from "@/lib/api";
import { PicksDay } from "@/lib/schemas";

export const picksKey = (day: string) => ["picks", day] as const;

export const picksQuery = (day: string) => ({
  queryKey: picksKey(day),
  queryFn: () => api(`/picks?date=${day}`, PicksDay),
  staleTime: 60_000, // matches the API's Cache-Control max-age
});

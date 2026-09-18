import { cookies } from "next/headers";

import { todayIn, TZ_COOKIE } from "@/lib/format";
import { Prefetched } from "@/lib/prefetch";
import { picksKey } from "@/lib/queries";
import { PicksDay } from "@/lib/schemas";

import { Dashboard } from "./dashboard-view";

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Server part of the dashboard: prefetches the requested day's picks so they are in the first paint. "Today" is
 * the viewer's date (time zone from the ap_tz cookie), the same day the browser will ask for. */
export default async function DashboardPage({ searchParams }: PageProps<"/dashboard">) {
  const raw = (await searchParams).date;
  const tz = (await cookies()).get(TZ_COOKIE)?.value;
  const day = typeof raw === "string" && DAY_RE.test(raw) ? raw : todayIn(tz ? decodeURIComponent(tz) : undefined);
  return (
    <Prefetched queries={[{ key: picksKey(day), path: `/picks?date=${day}`, schema: PicksDay }]}>
      <Dashboard />
    </Prefetched>
  );
}

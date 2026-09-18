import type { Metadata } from "next";
import { connection } from "next/server";

import { Disclaimer, PickCard } from "@/components/picks";
import { Alert, Card, Container, PageHeader } from "@/components/ui";
import { pct } from "@/lib/format";
import { TrackRecord } from "@/lib/schemas";
import { serverGet } from "@/lib/server-api";

export const metadata: Metadata = {
  title: "Track record",
  description: "Check every pick we have published against the real result, with the win rate by confidence level and by month. Nothing is hidden or deleted.",
  alternates: { canonical: "/track-record" },
};

const tierBar: Record<string, string> = { Strong: "bg-strong", Medium: "bg-medium", Lean: "bg-lean" };
const tierOrder = ["Strong", "Medium", "Lean"];

const won = (graded: number, rate: number | null) => (rate == null ? null : Math.round(rate * graded));

function monthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

export default async function TrackRecordPage() {
  await connection();
  const tr = await serverGet("/track-record", TrackRecord, { revalidate: 600, tags: ["track-record"] });
  if (!tr) {
    return (
      <Container className="py-16">
        <PageHeader title="Track record" />
        <Alert tone="warn">The track record could not be loaded right now. Please try again shortly.</Alert>
      </Container>
    );
  }
  const history = tierOrder.filter((t) => tr.backtest.tier_hit_rates[t] != null);
  const byTier = [...tr.by_tier].sort((a, b) => tierOrder.indexOf(a.tier) - tierOrder.indexOf(b.tier));
  const byMonth = [...tr.by_month].reverse();

  return (
    <Container className="space-y-12 py-16">
      <PageHeader
        title="Track record"
        subtitle="Every published prediction is graded against the real result and stays on record, including the misses."
      />

      <section aria-labelledby="live" className="space-y-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="live" className="text-xl font-bold">Live picks</h2>
          {tr.live_since ? <p className="text-sm text-muted">Tracking since {tr.live_since}</p> : null}
        </div>
        {tr.graded === 0 ? (
          <Alert>
            No live picks have been graded yet. Results appear here automatically after each matchday.
          </Alert>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Card><p className="text-xs text-muted">Picks graded</p><p className="num text-3xl font-bold">{tr.graded}</p></Card>
              <Card><p className="text-xs text-muted">Picks won</p><p className="num text-3xl font-bold">{won(tr.graded, tr.hit_rate) ?? "n/a"}</p></Card>
              <Card><p className="text-xs text-muted">Win rate</p><p className="num text-3xl font-bold">{pct(tr.hit_rate)}</p></Card>
            </div>
            {tr.graded < 200 ? (
              <p className="text-xs text-muted">Fewer than 200 graded picks so far, so these live figures are still early.</p>
            ) : null}

            <div className="grid gap-8 lg:grid-cols-2">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <caption className="mb-2 text-left font-semibold">By confidence tier</caption>
                  <thead className="text-xs text-muted">
                    <tr><th className="py-2">Tier</th><th>Picks</th><th>Won</th><th>Avg. confidence</th><th className="text-right">Win rate</th></tr>
                  </thead>
                  <tbody>
                    {byTier.map((t) => (
                      <tr key={t.tier} className="border-t border-border">
                        <td className="py-2 font-medium">{t.tier}</td>
                        <td className="num">{t.graded}</td>
                        <td className="num">{won(t.graded, t.hit_rate)}</td>
                        <td className="num">{pct(t.avg_confidence)}</td>
                        <td className="num text-right font-semibold">{pct(t.hit_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <caption className="mb-2 text-left font-semibold">By month</caption>
                  <thead className="text-xs text-muted">
                    <tr><th className="py-2">Month</th><th>Picks</th><th>Won</th><th className="text-right">Win rate</th></tr>
                  </thead>
                  <tbody>
                    {byMonth.map((m) => (
                      <tr key={m.month} className="border-t border-border">
                        <td className="py-2 font-medium">{monthLabel(m.month)}</td>
                        <td className="num">{m.graded}</td>
                        <td className="num">{won(m.graded, m.hit_rate)}</td>
                        <td className="num text-right font-semibold">{pct(m.hit_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="space-y-3">
              <h3 className="font-semibold">Latest results</h3>
              <div className="grid gap-4 md:grid-cols-2">
                {tr.recent.slice(0, 6).map((p) => <PickCard key={p.prediction_id} pick={p} />)}
              </div>
            </div>
          </>
        )}
      </section>

      <section aria-labelledby="history" className="space-y-4">
        <h2 id="history" className="text-xl font-bold">Results on past matches</h2>
        <Card className="space-y-5">
          <p className="text-sm text-muted">
            How often each tier of pick won
            {tr.backtest.matches ? <> across <span className="num">{tr.backtest.matches.toLocaleString("en-GB")}</span> past matches</> : null}.
          </p>
          <ul className="grid gap-6 sm:grid-cols-3">
            {history.map((tier) => {
              const rate = tr.backtest.tier_hit_rates[tier];
              return (
                <li key={tier}>
                  <p className="text-xs text-muted">{tier} picks</p>
                  <p className="num text-3xl font-bold">{pct(rate)}</p>
                  <div className="mt-2 h-1.5 bg-surface-2" aria-hidden="true">
                    <div className={`h-full ${tierBar[tier]}`} style={{ width: `${Math.round(rate * 100)}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-muted">Past results do not guarantee future ones.</p>
        </Card>
      </section>
      <Disclaimer />
    </Container>
  );
}

import type { Metadata } from "next";
import { connection } from "next/server";

import { Disclaimer, PickCard } from "@/components/picks";
import { Alert, Card, Container, PageHeader } from "@/components/ui";
import { pct } from "@/lib/format";
import { TrackRecord } from "@/lib/schemas";
import { serverGet } from "@/lib/server-api";

export const metadata: Metadata = {
  title: "Track record",
  description: "Every AlgoPredict prediction graded against the real result: hit rate by confidence tier, by month, and the out-of-sample backtest behind the model.",
  alternates: { canonical: "/track-record" },
};

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
  const bt = tr.backtest;
  return (
    <Container className="space-y-10 py-16">
      <PageHeader
        title="Track record"
        subtitle="Every published prediction is graded against the real result and stays on record, including the misses."
      />

      <section aria-labelledby="live" className="space-y-4">
        <h2 id="live" className="text-xl font-bold">Live predictions</h2>
        {tr.graded === 0 ? (
          <Alert>
            No live predictions have been graded yet. Results appear here automatically after each matchday
            {tr.live_since ? ` (tracking since ${tr.live_since})` : ""}.
          </Alert>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Card><p className="text-xs text-muted">Graded picks</p><p className="text-3xl font-bold tabular-nums">{tr.graded}</p></Card>
              <Card><p className="text-xs text-muted">Hit rate</p><p className="text-3xl font-bold tabular-nums">{pct(tr.hit_rate)}</p></Card>
              <Card><p className="text-xs text-muted">Mean RPS (lower is better)</p><p className="text-3xl font-bold tabular-nums">{tr.mean_rps?.toFixed(4) ?? "n/a"}</p></Card>
            </div>
            {tr.graded < 200 ? (
              <p className="text-xs text-muted">Fewer than 200 graded picks, so treat these live figures as early and noisy.</p>
            ) : null}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-left text-sm">
                <caption className="sr-only">Hit rate by confidence tier</caption>
                <thead className="text-xs text-muted">
                  <tr><th className="py-2">Tier</th><th>Graded</th><th>Avg. stated probability</th><th>Actual hit rate</th></tr>
                </thead>
                <tbody>
                  {tr.by_tier.map((t) => (
                    <tr key={t.tier} className="border-t border-border">
                      <td className="py-2 font-medium">{t.tier}</td><td>{t.graded}</td>
                      <td>{pct(t.avg_confidence)}</td><td>{pct(t.hit_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {tr.recent.slice(0, 6).map((p) => <PickCard key={p.prediction_id} pick={p} />)}
            </div>
          </>
        )}
      </section>

      <section aria-labelledby="backtest" className="space-y-4">
        <h2 id="backtest" className="text-xl font-bold">How the model was tested</h2>
        <Card className="space-y-3 text-sm">
          <p>
            Before going live, the model was evaluated walk-forward: trained only on seasons before each test season,
            then scored on {bt.source}. Its ranked probability score was <strong>{bt.model_rps.toFixed(5)}</strong> against
            <strong> {bt.bookmaker_rps.toFixed(5)}</strong> for bookmaker odds on the same matches. A small edge, not a
            magic one.
          </p>
          <div className="grid grid-cols-3 gap-4">
            {Object.entries(bt.tier_hit_rates).map(([tier, rate]) => (
              <div key={tier}><p className="text-xs text-muted">{tier} tier</p><p className="text-2xl font-bold tabular-nums">{pct(rate)}</p></div>
            ))}
          </div>
          <p className="text-xs text-muted">{bt.note}</p>
        </Card>
      </section>
      <Disclaimer />
    </Container>
  );
}

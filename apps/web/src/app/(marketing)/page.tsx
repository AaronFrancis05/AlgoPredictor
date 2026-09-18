import { BarChart3, CalendarDays, ListOrdered, ShieldCheck, Target, Trophy } from "lucide-react";
import type { Metadata } from "next";
import { connection } from "next/server";

import { JsonLd } from "@/components/json-ld";
import { Disclaimer, PickCard } from "@/components/picks";
import { ButtonLink, Card, Container } from "@/components/ui";
import { pct } from "@/lib/format";
import { PicksDay, TrackRecord } from "@/lib/schemas";
import { serverGet } from "@/lib/server-api";
import { site } from "@/lib/site";

export const metadata: Metadata = { alternates: { canonical: "/" } };

const features = [
  { icon: Target, title: "Slips to your target odd", text: "Enter the odds you want — say 10.0 — and get the 2–6 highest-probability picks whose combined odds land there. No padding with weak legs." },
  { icon: CalendarDays, title: "Weekly jackpot", text: "The two highest-confidence picks for every day of the week, with the combined probability shown honestly." },
  { icon: ListOrdered, title: "Daily top 10", text: "The ten single picks the model is most confident about today, each with its probability and tier." },
  { icon: BarChart3, title: "Real probabilities", text: "Every pick shows the model's home/draw/away probabilities, fair odds and the market price — not a vague 'banker'." },
  { icon: Trophy, title: "Public track record", text: "Every published prediction is graded against the real result and stays on record. Nothing is deleted." },
  { icon: ShieldCheck, title: "Built responsibly", text: "18+ only, no guaranteed-win claims, and clear tools to keep betting under control." },
];

const faq = [
  { q: "How accurate are the predictions?", a: "In an out-of-sample test on 38,732 main-league matches (2021/22–2025/26), picks the model rated Strong won about 74.5% of the time, Medium about 57% and Lean about 42%. No model wins every match; we show the real numbers." },
  { q: "Where do the predictions come from?", a: "A gradient-boosted machine-learning model trained on two decades of results, form, team strength and market prices across 22 European leagues. It is retrained weekly and only replaces the previous model when it tests better." },
  { q: "Can I cancel any time?", a: "Yes. Card subscriptions are managed in the billing portal and mobile-money plans simply stop renewing. You keep access until the end of the paid period." },
  { q: "Do you take bets?", a: "No. AlgoPredict provides information only. You place any bets yourself with a licensed bookmaker where betting is legal for you." },
];

export default async function Home() {
  await connection(); // per-request render (CSP nonce); data below comes from the tagged fetch cache
  const [today, record] = await Promise.all([
    serverGet("/picks", PicksDay, { revalidate: 120, tags: ["picks"] }),
    serverGet("/track-record", TrackRecord, { revalidate: 600, tags: ["track-record"] }),
  ]);
  const teaser = today?.picks.slice(0, 3) ?? [];
  const rates = record?.backtest.tier_hit_rates ?? { Strong: 0.745, Medium: 0.57, Lean: 0.419 };

  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@graph": [
            { "@type": "Organization", name: site.name, url: site.url },
            { "@type": "WebSite", name: site.name, url: site.url },
            { "@type": "FAQPage", mainEntity: faq.map((f) => ({ "@type": "Question", name: f.q,
                                                              acceptedAnswer: { "@type": "Answer", text: f.a } })) },
          ],
        }}
      />
      <section className="border-b border-border bg-[radial-gradient(ellipse_at_top,rgba(34,197,94,0.15),transparent_60%)]">
        <Container className="grid items-center gap-12 py-20 lg:grid-cols-2">
          <div>
            <p className="mb-4 inline-flex rounded-full border border-border px-3 py-1 text-xs text-muted">
              Tested on 38,732 matches · retrained every week
            </p>
            <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">
              Football predictions with the <span className="text-brand">probability</span> behind every pick.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-muted">
              A machine-learning model rates every fixture. You see its real confidence, build slips to the odds you
              want, and check every past pick against the result.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href="/register">Get today&apos;s free picks</ButtonLink>
              <ButtonLink href="/track-record" variant="secondary">See the track record</ButtonLink>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-4">
              {(["Strong", "Medium", "Lean"] as const).map((t) => (
                <div key={t}>
                  <dt className="text-xs text-muted">{t} tier hit rate</dt>
                  <dd className="text-2xl font-bold tabular-nums">{pct(rates[t], 0)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-muted">Out-of-sample backtest, 2021/22–2025/26. Past results do not guarantee future ones.</p>
          </div>
          <div className="space-y-4">
            {teaser.length ? (
              teaser.map((p) => <PickCard key={p.prediction_id} pick={p} />)
            ) : (
              <Card className="py-10 text-center">
                <p className="font-semibold">Today&apos;s picks are published before kick-off</p>
                <p className="mt-2 text-sm text-muted">Create a free account to see them as soon as they are released.</p>
              </Card>
            )}
          </div>
        </Container>
      </section>

      <Container className="py-20">
        <h2 className="text-3xl font-bold tracking-tight">Three ways to use the model</h2>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(({ icon: Icon, title, text }) => (
            <Card key={title}>
              <Icon className="h-6 w-6 text-brand" aria-hidden />
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-2 text-sm text-muted">{text}</p>
            </Card>
          ))}
        </div>
      </Container>

      <Container className="py-10">
        <h2 className="text-3xl font-bold tracking-tight">Questions</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {faq.map((f) => (
            <Card key={f.q}>
              <h3 className="font-semibold">{f.q}</h3>
              <p className="mt-2 text-sm text-muted">{f.a}</p>
            </Card>
          ))}
        </div>
        <div className="mt-10 flex flex-col items-start gap-4 rounded-card border border-border bg-surface p-8 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xl font-bold">Start with three free picks a day.</p>
            <p className="text-sm text-muted">Upgrade to Pro or Elite when you want the full slate.</p>
          </div>
          <ButtonLink href="/pricing">Compare plans</ButtonLink>
        </div>
        <div className="mt-8">
          <Disclaimer />
        </div>
      </Container>
    </>
  );
}

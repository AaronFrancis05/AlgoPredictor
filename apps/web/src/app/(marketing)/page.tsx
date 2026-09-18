import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { JsonLd } from "@/components/json-ld";
import { Disclaimer, PickCard } from "@/components/picks";
import { ButtonLink, Container } from "@/components/ui";
import { pct } from "@/lib/format";
import { PicksDay, TrackRecord } from "@/lib/schemas";
import { serverGet } from "@/lib/server-api";
import { site } from "@/lib/site";

export const metadata: Metadata = { alternates: { canonical: "/" } };

const features = [
  { title: "Slips to your target odd", text: "Enter the odds you want, say 10.0, and get the 2 to 6 highest-probability picks whose combined odds land there. Weak legs are never added just to reach the number." },
  { title: "Weekly jackpot", text: "The two highest-confidence picks for every day of the week, with the combined probability shown as it is." },
  { title: "Daily top 10", text: "The ten single picks the model is most confident about today, each with its probability and tier." },
  { title: "The numbers behind each pick", text: "Home, draw and away probabilities, fair odds and the market price for every fixture, not a vague 'banker'." },
  { title: "Public track record", text: "Every published prediction is graded against the real result and stays on record. Nothing is deleted." },
  { title: "Built responsibly", text: "18+ only, no guaranteed-win claims, and clear tools to keep betting under control." },
];

const faq = [
  { q: "How accurate are the predictions?", a: "In an out-of-sample test on 38,732 main-league matches (2021/22 to 2025/26), picks the model rated Strong won about 74.5% of the time, Medium about 57% and Lean about 42%. No model wins every match; we show the real numbers." },
  { q: "Where do the predictions come from?", a: "A gradient-boosted machine-learning model trained on two decades of results, form, team strength and market prices across 22 European leagues. It is retrained weekly and only replaces the previous model when it tests better." },
  { q: "Can I cancel any time?", a: "Yes. Card subscriptions are managed in the billing portal and mobile-money plans simply stop renewing. You keep access until the end of the paid period." },
  { q: "Do you take bets?", a: "No. AlgoPredict provides information only. You place any bets yourself with a licensed bookmaker where betting is legal for you." },
];

const tiers = [
  { tier: "Strong", rule: "65% or more" },
  { tier: "Medium", rule: "50 to 65%" },
  { tier: "Lean", rule: "under 50%" },
] as const;

export default async function Home() {
  await connection(); // per-request render (CSP nonce); data below comes from the tagged fetch cache
  const [today, record] = await Promise.all([
    serverGet("/picks", PicksDay, { revalidate: 120, tags: ["picks"] }),
    serverGet("/track-record", TrackRecord, { revalidate: 600, tags: ["track-record"] }),
  ]);
  const teaser = today?.picks.slice(0, 3) ?? [];
  const rates = record?.backtest.tier_hit_rates ?? { Strong: 0.745, Medium: 0.57, Lean: 0.419 };
  const bt = record?.backtest;

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
      <section className="border-b border-border">
        <Container className="grid gap-14 py-16 lg:grid-cols-[1.15fr_1fr] lg:py-24">
          <div>
            <p className="num text-xs uppercase tracking-widest text-muted">22 European leagues · retrained weekly</p>
            <h1 className="mt-5 max-w-xl text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-[3.4rem]">
              Football predictions with the probability behind every pick.
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-muted">
              A machine-learning model rates every fixture. You see its real confidence, build slips to the odds you
              want, and check every past pick against the result.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <ButtonLink href="/register">Get today&apos;s free picks</ButtonLink>
              <ButtonLink href="/track-record" variant="secondary">See the track record</ButtonLink>
            </div>
          </div>

          <figure className="self-center border border-border bg-surface">
            <figcaption className="flex items-baseline justify-between border-b border-border px-5 py-3">
              <span className="text-sm font-semibold">Out-of-sample backtest</span>
              <span className="num text-xs text-muted">38,732 matches</span>
            </figcaption>
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="px-5 py-2.5 font-medium">Tier</th>
                  <th className="px-5 py-2.5 font-medium">Model probability</th>
                  <th className="px-5 py-2.5 text-right font-medium">Picks won</th>
                </tr>
              </thead>
              <tbody>
                {tiers.map((t) => (
                  <tr key={t.tier} className="border-t border-border">
                    <td className="px-5 py-3 font-semibold">{t.tier}</td>
                    <td className="px-5 py-3 text-muted">{t.rule}</td>
                    <td className="num px-5 py-3 text-right text-lg font-semibold">{pct(rates[t.tier], 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {bt ? (
              <dl className="grid grid-cols-2 border-t border-border text-sm">
                <div className="border-r border-border px-5 py-3">
                  <dt className="text-xs text-muted">Model RPS</dt>
                  <dd className="num mt-0.5 font-semibold">{bt.model_rps.toFixed(5)}</dd>
                </div>
                <div className="px-5 py-3">
                  <dt className="text-xs text-muted">Bookmaker RPS</dt>
                  <dd className="num mt-0.5 font-semibold">{bt.bookmaker_rps.toFixed(5)}</dd>
                </div>
              </dl>
            ) : null}
            <p className="border-t border-border px-5 py-3 text-xs text-muted">
              Seasons 2021/22 to 2025/26, each scored by a model trained only on earlier seasons. Lower RPS is better.
              Past results do not guarantee future ones.
            </p>
          </figure>
        </Container>
      </section>

      {teaser.length ? (
        <Container className="pt-16">
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="text-2xl font-bold tracking-tight">Today&apos;s first picks</h2>
            <Link href="/register" className="text-sm text-muted underline underline-offset-4 hover:text-fg">See the full slate</Link>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {teaser.map((p) => <PickCard key={p.prediction_id} pick={p} />)}
          </div>
        </Container>
      ) : null}

      <Container className="grid gap-10 py-20 lg:grid-cols-[1fr_2fr]">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">What you get</h2>
          <p className="mt-3 max-w-xs text-muted">One model, one pick per fixture, and the probability it actually computed.</p>
        </div>
        <dl className="grid gap-x-10 sm:grid-cols-2">
          {features.map((f) => (
            <div key={f.title} className="border-t border-border py-5">
              <dt className="font-semibold">{f.title}</dt>
              <dd className="mt-1.5 text-sm leading-relaxed text-muted">{f.text}</dd>
            </div>
          ))}
        </dl>
      </Container>

      <section className="border-y border-border bg-surface">
        <Container className="grid gap-10 py-20 lg:grid-cols-[1fr_2fr]">
          <h2 className="text-3xl font-bold tracking-tight">Questions</h2>
          <dl className="divide-y divide-border">
            {faq.map((f) => (
              <div key={f.q} className="py-5 first:pt-0">
                <dt className="font-semibold">{f.q}</dt>
                <dd className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">{f.a}</dd>
              </div>
            ))}
          </dl>
        </Container>
      </section>

      <Container className="py-16">
        <div className="flex flex-col items-start gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-2xl font-bold tracking-tight">Start with three free picks a day.</p>
            <p className="mt-1 text-muted">Upgrade to Pro or Elite when you want the full slate.</p>
          </div>
          <ButtonLink href="/pricing">Compare plans</ButtonLink>
        </div>
        <div className="mt-10">
          <Disclaimer />
        </div>
      </Container>
    </>
  );
}

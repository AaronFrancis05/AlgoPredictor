import type { Metadata } from "next";
import { connection } from "next/server";

import { JsonLd } from "@/components/json-ld";
import { Disclaimer } from "@/components/picks";
import { SessionCta } from "@/components/session-actions";
import { ButtonLink, Container } from "@/components/ui";
import { pct } from "@/lib/format";
import { TrackRecord } from "@/lib/schemas";
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
  { q: "How accurate are the predictions?", a: "Across 38,732 past matches, Strong picks won about 74.5% of the time, Medium about 57% and Lean about 42%. No model wins every match; we show the real numbers, and every live pick is graded on the track record page." },
  { q: "Where do the predictions come from?", a: "Our own machine-learning model, built on years of football results. It is updated regularly and a new version only goes live when it performs better than the current one." },
  { q: "Can I cancel any time?", a: "Yes. Card subscriptions are managed in the billing portal and mobile-money plans simply stop renewing. You keep access until the end of the paid period." },
  { q: "Do you take bets?", a: "No. AlgoPredict provides information only. You place any bets yourself with a licensed bookmaker where betting is legal for you." },
];

const tiers = [
  { tier: "Strong", rule: "65% or more confident", bar: "bg-strong" },
  { tier: "Medium", rule: "50 to 65% confident", bar: "bg-medium" },
  { tier: "Lean", rule: "under 50% confident", bar: "bg-lean" },
] as const;

export default async function Home() {
  await connection(); // per-request render (CSP nonce); data below comes from the tagged fetch cache
  const record = await serverGet("/track-record", TrackRecord, { revalidate: 600, tags: ["track-record"] });
  const rates = record?.backtest.tier_hit_rates ?? { Strong: 0.745, Medium: 0.57, Lean: 0.419 };
  const matches = record?.backtest.matches ?? 38732;
  const live = record && record.graded > 0 && record.hit_rate != null ? record : null;

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
            <p className="num text-xs uppercase tracking-widest text-muted">Every pick graded against the real result</p>
            <h1 className="mt-5 max-w-xl text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-[3.4rem]">
              Football predictions with the probability behind every pick.
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-muted">
              A machine-learning model rates every fixture. You see its real confidence, build slips to the odds you
              want, and check every past pick against the result.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <SessionCta signedOutHref="/register" signedOut={<>Get today&apos;s free picks</>} />
              <ButtonLink href="/track-record" variant="secondary">See the track record</ButtonLink>
            </div>
          </div>

          <figure className="self-center rounded-card border border-border bg-surface">
            <figcaption className="border-b border-border px-6 py-5">
              <p className="text-xs uppercase tracking-widest text-muted">Our results</p>
              <p className="mt-1.5 text-xl font-bold tracking-tight">How often our picks win</p>
            </figcaption>
            <ul className="divide-y divide-border">
              {tiers.map((t) => {
                const rate = rates[t.tier];
                return (
                  <li key={t.tier} className="px-6 py-4">
                    <div className="flex items-baseline justify-between gap-4">
                      <div>
                        <p className="font-semibold">{t.tier} picks</p>
                        <p className="text-xs text-muted">{t.rule}</p>
                      </div>
                      <p className="num text-3xl font-bold tabular-nums">{pct(rate, 1)}</p>
                    </div>
                    <div className="mt-3 h-1.5 bg-surface-2" aria-hidden="true">
                      <div className={`h-full ${t.bar}`} style={{ width: `${Math.round((rate ?? 0) * 100)}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="border-t border-border bg-surface-2 px-6 py-4 text-sm">
              {live ? (
                <p>
                  <span className="font-semibold">Live so far:</span>{" "}
                  <span className="num">{Math.round((live.hit_rate ?? 0) * live.graded)}</span> of{" "}
                  <span className="num">{live.graded}</span> published picks won ({pct(live.hit_rate, 1)}).
                </p>
              ) : (
                <p>
                  <span className="font-semibold">Live tracking is on.</span> Every new pick is graded after the
                  final whistle{record?.live_since ? ` (since ${record.live_since})` : ""}.
                </p>
              )}
            </div>
            <p className="border-t border-border px-6 py-3 text-xs text-muted">
              Based on <span className="num">{matches.toLocaleString("en-GB")}</span> past matches. Past results do not
              guarantee future ones.
            </p>
          </figure>
        </Container>
      </section>

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

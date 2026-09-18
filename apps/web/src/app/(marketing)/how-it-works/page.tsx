import type { Metadata } from "next";

import { Disclaimer } from "@/components/picks";
import { ButtonLink, Card, Container, PageHeader } from "@/components/ui";

export const metadata: Metadata = {
  title: "How it works",
  description: "How AlgoPredict's football model works: data, training, weekly retraining, confidence tiers, the target-odds slip builder and the weekly jackpot.",
  alternates: { canonical: "/how-it-works" },
};

const steps = [
  { t: "1. Data", d: "Two decades of results, shots, form, rest days, head-to-head records, club strength ratings and pre-match odds across 22 European leagues." },
  { t: "2. Model", d: "Gradient-boosted trees (CatBoost/LightGBM) estimate the probability of a home win, draw and away win for every fixture. Hyper-parameters are tuned on a season the model never evaluates on." },
  { t: "3. Honest testing", d: "Walk-forward validation: the model is trained only on the past and tested on the next season, five seasons in a row — 38,732 matches it had never seen." },
  { t: "4. Weekly learning", d: "After every round, predictions are graded against real results. A retrained challenger replaces the current model only if it scores better on matches neither has seen." },
];

export default function HowItWorks() {
  return (
    <Container className="space-y-12 py-16">
      <PageHeader title="How it works" subtitle="From historical data to a probability for tonight's match." />
      <div className="grid gap-5 md:grid-cols-2">
        {steps.map((s) => (
          <Card key={s.t}><h2 className="font-semibold">{s.t}</h2><p className="mt-2 text-sm text-muted">{s.d}</p></Card>
        ))}
      </div>

      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Confidence tiers</h2>
        <p className="max-w-3xl text-muted">
          Each pick is the outcome with the highest model probability. Its tier describes how sure the model is:
          <strong className="text-fg"> Strong</strong> (≥ 65%), <strong className="text-fg">Medium</strong> (50–65%) and
          <strong className="text-fg"> Lean</strong> (&lt; 50%). The probability shown is always the model&apos;s real
          number — we never round it up to sound more certain.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-bold">The slip builder and the weekly jackpot</h2>
        <p className="max-w-3xl text-muted">
          Tell the slip builder the total odds you want and it searches upcoming picks (one per match, odds 1.20–2.50)
          for the combination with the highest combined probability that lands within your target range. If none fits,
          it says so instead of padding the slip. The weekly jackpot takes the two highest-confidence picks for each day.
          Combined probabilities multiply the legs and assume the matches are independent — and they fall quickly as you
          add legs.
        </p>
      </section>
      <ButtonLink href="/register">Try it free</ButtonLink>
      <Disclaimer />
    </Container>
  );
}

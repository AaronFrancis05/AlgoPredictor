import type { Metadata } from "next";

import { Disclaimer } from "@/components/picks";
import { ButtonLink, Container, PageHeader } from "@/components/ui";

export const metadata: Metadata = {
  title: "How it works",
  description: "How AlgoPredict works: a probability for every fixture, confidence tiers, a public track record, the target-odds slip builder and the weekly jackpot.",
  alternates: { canonical: "/how-it-works" },
};

const steps = [
  { t: "1. Every fixture is rated", d: "Our own machine-learning model gives each match a probability for a home win, a draw and an away win." },
  { t: "2. One clear pick", d: "The pick is the outcome with the highest probability, with a confidence tier so you can see at a glance how sure the model is." },
  { t: "3. Checked against the result", d: "After the final whistle every published pick is graded and added to the public track record. Nothing is edited or deleted." },
  { t: "4. Always improving", d: "The model is updated regularly, and a new version only goes live when it performs better than the current one." },
];

export default function HowItWorks() {
  return (
    <Container className="space-y-12 py-16">
      <PageHeader title="How it works" subtitle="A probability for every match, one clear pick, and a record you can check." />
      <ol className="grid gap-x-10 md:grid-cols-2">
        {steps.map((s) => (
          <li key={s.t} className="border-t border-border py-6">
            <h2 className="font-semibold">{s.t}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{s.d}</p>
          </li>
        ))}
      </ol>

      <section className="space-y-4">
        <h2 className="text-2xl font-bold">Confidence tiers</h2>
        <p className="max-w-3xl text-muted">
          Each pick is the outcome with the highest model probability. Its tier describes how sure the model is:
          <strong className="text-fg"> Strong</strong> (65% or more), <strong className="text-fg">Medium</strong> (50 to 65%) and
          <strong className="text-fg"> Lean</strong> (under 50%). The probability shown is always the model&apos;s real
          number. We never round it up to sound more certain.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-bold">The slip builder and the weekly jackpot</h2>
        <p className="max-w-3xl text-muted">
          Tell the slip builder the total odds you want and it searches upcoming picks (one per match, odds 1.20 to 2.50)
          for the combination with the highest combined probability that lands within your target range. If none fits,
          it says so instead of padding the slip. The weekly jackpot takes the two highest-confidence picks for each day.
          Combined probabilities multiply the legs and assume the matches are independent, and they fall quickly as you
          add legs.
        </p>
      </section>
      <ButtonLink href="/register">Try it free</ButtonLink>
      <Disclaimer />
    </Container>
  );
}

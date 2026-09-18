import type { Metadata } from "next";

import { Card, Container, PageHeader } from "@/components/ui";

export const metadata: Metadata = {
  title: "Responsible gambling",
  description: "Keep betting safe: AlgoPredict is 18+ only, never guarantees results, and points you to free, confidential help.",
  alternates: { canonical: "/responsible-gambling" },
};

const tips = [
  "Only bet money you can afford to lose. Set a budget before you start and stop when it is gone.",
  "No prediction is certain. Even our Strong tier loses roughly one match in four in historical testing.",
  "Never chase losses by betting more to win back what you lost.",
  "Longer accumulators pay more because they lose far more often.",
  "Take breaks. Use deposit limits and self-exclusion tools offered by licensed bookmakers.",
];

const help = [
  { name: "BeGambleAware (UK)", url: "https://www.begambleaware.org" },
  { name: "GamCare (UK)", url: "https://www.gamcare.org.uk" },
  { name: "Gamblers Anonymous (international)", url: "https://www.gamblersanonymous.org" },
  { name: "Responsible Gambling Council", url: "https://www.responsiblegambling.org" },
];

export default function ResponsibleGambling() {
  return (
    <Container className="max-w-3xl space-y-8 py-16">
      <PageHeader title="Responsible gambling" subtitle="AlgoPredict is for adults (18+) and provides information, not bets." />
      <Card>
        <ul className="list-disc space-y-2 pl-5 text-sm">{tips.map((t) => <li key={t}>{t}</li>)}</ul>
      </Card>
      <section className="space-y-3">
        <h2 className="text-xl font-bold">Free, confidential help</h2>
        <ul className="space-y-2 text-sm">
          {help.map((h) => (
            <li key={h.url}><a className="text-accent underline" href={h.url} rel="noopener noreferrer" target="_blank">{h.name}</a></li>
          ))}
        </ul>
        <p className="text-sm text-muted">
          Want to stop using AlgoPredict? You can delete your account at any time from Account → Delete account.
        </p>
      </section>
    </Container>
  );
}

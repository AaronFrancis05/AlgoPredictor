import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Container, PageHeader } from "@/components/ui";
import { site } from "@/lib/site";

/**
 * TEMPLATE legal text. It describes how the product actually works, but it is not legal advice:
 * have a lawyer review it for every jurisdiction you sell in before launch.
 */
const docs = {
  terms: {
    title: "Terms of service",
    sections: [
      ["The service", `${site.name} publishes statistical predictions for football matches. It is an information service. We do not accept, place or broker bets.`],
      ["Eligibility", "You must be at least 18 years old (or the legal age in your country, if higher) and allowed to use betting-related information where you live."],
      ["No guarantee", "Predictions are probabilities produced by a statistical model. They can be and often are wrong. Past performance does not guarantee future results. You are solely responsible for any bet you place."],
      ["Subscriptions", "Paid plans renew automatically each period until cancelled. You keep access until the end of the period you paid for. Card subscriptions are managed in the billing portal."],
      ["Acceptable use", "Do not resell, scrape or redistribute predictions, share accounts, or attempt to bypass rate limits or security controls. API access is for the subscriber's own use."],
      ["Changes", "We may update these terms; material changes are announced by email before they take effect."],
    ],
  },
  privacy: {
    title: "Privacy policy",
    sections: [
      ["What we collect", "Email, optional name and country, a hashed password (Argon2id), subscription status, and security logs (sign-ins, IP address). Payment card data is handled by Stripe or Flutterwave and never reaches our servers."],
      ["Why", "To run your account, provide the plan you pay for, prevent fraud and abuse, and meet legal obligations."],
      ["Cookies", "Strictly necessary cookies only: a short-lived session cookie, a refresh cookie and a CSRF-protection cookie. No advertising trackers."],
      ["Your rights", "You can download all data we hold about you and delete your account at any time from the Account page."],
      // keep the period in step with ACCOUNT_RETENTION_DAYS on the API
      ["Retention", "When you close your account it is disabled at once: you are signed out everywhere and no one can sign in to it. We keep the account data for 30 days for legal and record-keeping purposes (and so it can be restored if you ask), then erase it permanently. Payment records are kept without your identity for as long as accounting and tax law requires."],
      ["Contact", `Questions: ${site.supportEmail}`],
    ],
  },
} as const;

type Doc = keyof typeof docs;

export function generateStaticParams() {
  return Object.keys(docs).map((doc) => ({ doc }));
}

export async function generateMetadata({ params }: PageProps<"/legal/[doc]">): Promise<Metadata> {
  const { doc } = await params;
  const d = docs[doc as Doc];
  return d ? { title: d.title, alternates: { canonical: `/legal/${doc}` } } : {};
}

export default async function LegalPage({ params }: PageProps<"/legal/[doc]">) {
  const { doc } = await params;
  const d = docs[doc as Doc];
  if (!d) notFound();
  return (
    <Container className="max-w-3xl py-16">
      <PageHeader title={d.title} subtitle="Last updated September 2026" />
      <div className="space-y-6 text-sm leading-relaxed">
        {d.sections.map(([h, body]) => (
          <section key={h}>
            <h2 className="mb-1 text-base font-semibold">{h}</h2>
            <p className="text-muted">{body}</p>
          </section>
        ))}
      </div>
    </Container>
  );
}

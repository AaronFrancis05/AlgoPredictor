import type { Metadata } from "next";
import { connection } from "next/server";
import { z } from "zod";

import { JsonLd } from "@/components/json-ld";
import { Disclaimer } from "@/components/picks";
import { Alert, Container, PageHeader } from "@/components/ui";
import { Plan } from "@/lib/schemas";
import { serverGet } from "@/lib/server-api";
import { site } from "@/lib/site";

import { PricingTable } from "./pricing-table";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Free, Pro and Elite plans for AlgoPredict football predictions. Pay by card worldwide or mobile money in Africa. Cancel any time.",
  alternates: { canonical: "/pricing" },
};

export default async function PricingPage() {
  await connection();
  const plans = await serverGet("/plans", z.array(Plan), { revalidate: 600, tags: ["plans"] });
  return (
    <Container className="py-16">
      <PageHeader
        title="Simple plans. Honest numbers."
        subtitle="Start free. Upgrade when you want every pick, the slip builder and the weekly jackpot."
      />
      {plans ? (
        <>
          <JsonLd
            data={{
              "@context": "https://schema.org",
              "@type": "Product",
              name: `${site.name} subscription`,
              description: site.description,
              offers: plans.flatMap((p) =>
                p.prices.filter((x) => x.currency === "USD").map((x) => ({
                  "@type": "Offer", name: `${p.name} (${x.interval}ly)`, priceCurrency: "USD",
                  price: (x.amount_minor / 100).toFixed(2), availability: "https://schema.org/InStock",
                  url: `${site.url}/pricing`,
                })),
              ),
            }}
          />
          <PricingTable plans={plans} />
        </>
      ) : (
        <Alert tone="warn">Plans could not be loaded right now. Please try again in a moment.</Alert>
      )}
      <div className="mt-10 space-y-3 text-sm text-muted">
        <p>
          Prices include no hidden fees. Card payments are processed by Stripe; mobile money and African cards by
          Flutterwave. We never see or store your card details.
        </p>
        <Disclaimer />
      </div>
    </Container>
  );
}

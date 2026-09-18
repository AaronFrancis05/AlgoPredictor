"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { z } from "zod";

import { Disclaimer } from "@/components/picks";
import { PricingTable } from "@/components/pricing-table";
import { Alert, ButtonLink, PageHeader, Spinner } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { Plan } from "@/lib/schemas";

function CheckoutNotice() {
  const status = useSearchParams().get("checkout");
  if (status === "cancelled") return <Alert>Checkout was cancelled. Nothing was charged.</Alert>;
  return null;
}

/** Plans for signed-in users: same cards as the public pricing page, but aware of the plan they are on. */
export default function Plans() {
  const me = useMe();
  const q = useQuery({ queryKey: ["plans"], queryFn: () => api("/plans", z.array(Plan)), staleTime: 600_000 });
  const user = me.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Plans"
        subtitle={user?.is_admin
          ? "Admin account: every feature is included and nothing is billed."
          : "Upgrade for every pick, the slip builder and the weekly jackpot. Cancel any time."}
        action={<ButtonLink href="/account/billing" variant="secondary">Billing</ButtonLink>}
      />
      <Suspense fallback={null}><CheckoutNotice /></Suspense>
      {q.isLoading ? <Spinner /> : null}
      {q.error ? <ErrorPanel error={q.error} /> : null}
      {q.data && user ? <PricingTable plans={q.data} current={user.plan} isAdmin={user.is_admin} /> : null}
      <div className="space-y-3 text-sm text-muted">
        <p>
          Card payments are processed by Stripe; mobile money and African cards by Flutterwave. We never see or
          store your card details. To downgrade or cancel, use Billing.
        </p>
        <Disclaimer />
      </div>
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { z } from "zod";

import { Alert, Button, ButtonLink, Card, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { Redirect, Subscription } from "@/lib/schemas";

function CheckoutNotice() {
  const status = useSearchParams().get("checkout");
  if (status === "success") return <Alert tone="success">Payment received. Your plan updates as soon as the provider confirms it (usually within a minute).</Alert>;
  if (status === "processing") return <Alert>Your payment is being confirmed. This page updates once it clears.</Alert>;
  return null;
}

export default function Billing() {
  const [error, setError] = useState<string | null>(null);
  const user = useMe().data;
  const q = useQuery({
    queryKey: ["subscriptions"],
    queryFn: () => api("/billing/subscription", z.array(Subscription)),
    refetchInterval: (query) => (query.state.data?.some((s) => s.status === "active") ? false : 15_000),
  });

  async function portal() {
    setError(null);
    try {
      window.location.assign((await api("/billing/portal", Redirect, { method: "POST" })).url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open the billing portal");
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader title="Billing" subtitle="Your subscriptions and payment settings." action={<ButtonLink href="/account/plans">Change plan</ButtonLink>} />
      <Suspense fallback={null}><CheckoutNotice /></Suspense>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {q.isLoading ? <Spinner /> : null}
      {q.error ? <ErrorPanel error={q.error} /> : null}
      {q.data && q.data.length === 0 && user ? (
        <EmptyState title="No paid subscription">
          {user.is_admin
            ? "Admin account: every feature is included and nothing is billed."
            : user.plan === "free"
              ? "You are on the Free plan."
              : <>You are on the <span className="capitalize">{user.plan}</span> plan without a paid subscription (for example from an access code).</>}
        </EmptyState>
      ) : null}
      {q.data?.map((s, i) => (
        <Card key={i} className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="font-semibold capitalize">{s.plan_code} · {s.provider}</p>
            <p className="text-sm text-muted">
              Status: {s.status}
              {s.current_period_end ? ` · ${s.cancel_at_period_end ? "ends" : "renews"} ${new Date(s.current_period_end).toLocaleDateString()}` : ""}
            </p>
          </div>
          {s.provider === "stripe" ? <Button variant="secondary" onClick={portal}>Manage card subscription</Button> : null}
        </Card>
      ))}
    </div>
  );
}

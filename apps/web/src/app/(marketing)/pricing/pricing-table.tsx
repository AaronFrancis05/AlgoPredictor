"use client";

import { Check, Minus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Alert, Badge, Button, Card } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { cn, formatPrice } from "@/lib/format";
import { type Plan, Redirect } from "@/lib/schemas";

const featureRows: { key: keyof Plan["entitlements"] | "all_picks"; label: string }[] = [
  { key: "all_picks", label: "Every daily pick" },
  { key: "top10", label: "Daily top 10" },
  { key: "slip_builder", label: "Target-odds slip builder" },
  { key: "jackpot", label: "Weekly jackpot (2 picks/day)" },
  { key: "value_flags", label: "VALUE flags vs market odds" },
  { key: "api_access", label: "API access" },
];

function hasFeature(plan: Plan, key: (typeof featureRows)[number]["key"]) {
  if (key === "all_picks") return plan.entitlements.picks_per_day === null;
  return Boolean(plan.entitlements[key]);
}

export function PricingTable({ plans }: { plans: Plan[] }) {
  const router = useRouter();
  const currencies = useMemo(
    () => Array.from(new Set(plans.flatMap((p) => p.prices.map((x) => x.currency)))).sort(),
    [plans],
  );
  const [currency, setCurrency] = useState(currencies.includes("USD") ? "USD" : currencies[0] ?? "USD");
  const [interval, setInterval] = useState<"month" | "year">("month");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function checkout(plan: Plan, provider: "stripe" | "flutterwave") {
    setError(null);
    setBusy(`${plan.code}:${provider}`);
    try {
      const { url } = await api("/billing/checkout", Redirect, {
        method: "POST",
        json: { plan_code: plan.code, currency, interval, provider },
      });
      window.location.assign(url);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.push(`/register?plan=${plan.code}`);
        return;
      }
      setError(e instanceof Error ? e.message : "Checkout failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted" htmlFor="currency">Currency</label>
        <select
          id="currency"
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
          className="rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm"
        >
          {currencies.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <div role="radiogroup" aria-label="Billing interval" className="flex rounded-xl border border-border p-1">
          {(["month", "year"] as const).map((i) => (
            <button
              key={i}
              role="radio"
              aria-checked={interval === i}
              onClick={() => setInterval(i)}
              className={cn("rounded-lg px-3 py-1.5 text-sm", interval === i ? "bg-surface-2 font-semibold" : "text-muted")}
            >
              {i === "month" ? "Monthly" : "Yearly"}
            </button>
          ))}
        </div>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}

      <div className="grid gap-5 lg:grid-cols-3">
        {plans.map((plan) => {
          const price = plan.prices.find((x) => x.currency === currency && x.interval === interval);
          const featured = plan.code === "pro";
          return (
            <Card key={plan.code} className={cn("flex flex-col", featured && "border-brand shadow-lg shadow-brand/10")}>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold">{plan.name}</h2>
                {featured ? <Badge className="border-brand/50 text-brand">Most popular</Badge> : null}
              </div>
              <p className="mt-2 min-h-10 text-sm text-muted">{plan.description}</p>
              <p className="mt-6 text-3xl font-extrabold tabular-nums">
                {plan.code === "free" ? "Free" : price ? formatPrice(price.amount_minor, price.currency) : "—"}
                {plan.code !== "free" && price ? (
                  <span className="text-sm font-medium text-muted">/{interval === "month" ? "mo" : "yr"}</span>
                ) : null}
              </p>
              {plan.code !== "free" && !price ? (
                <p className="mt-1 text-xs text-muted">Not offered {interval === "year" ? "yearly" : "monthly"} in {currency}.</p>
              ) : null}
              <ul className="mt-6 flex-1 space-y-2.5 text-sm">
                {plan.code === "free" ? (
                  <li className="flex gap-2"><Check className="h-4 w-4 text-brand" aria-hidden /> 3 picks a day, 2h before kick-off</li>
                ) : null}
                {featureRows.map((f) => {
                  const on = hasFeature(plan, f.key);
                  return (
                    <li key={f.key} className={cn("flex gap-2", !on && "text-muted")}>
                      {on ? <Check className="h-4 w-4 text-brand" aria-hidden /> : <Minus className="h-4 w-4" aria-hidden />}
                      <span>
                        {f.label}
                        {f.key === "slip_builder" && on && plan.entitlements.slips_per_day
                          ? ` (${plan.entitlements.slips_per_day}/day)`
                          : ""}
                        <span className="sr-only">{on ? " included" : " not included"}</span>
                      </span>
                    </li>
                  );
                })}
              </ul>
              <div className="mt-6 space-y-2">
                {plan.code === "free" ? (
                  <Button variant="secondary" className="w-full" onClick={() => router.push("/register")}>
                    Create free account
                  </Button>
                ) : price && price.providers.length ? (
                  <>
                    {price.providers.includes("stripe") ? (
                      <Button className="w-full" disabled={busy !== null} onClick={() => checkout(plan, "stripe")}>
                        {busy === `${plan.code}:stripe` ? "Redirecting…" : "Pay by card"}
                      </Button>
                    ) : null}
                    {price.providers.includes("flutterwave") ? (
                      <Button variant="secondary" className="w-full" disabled={busy !== null}
                              onClick={() => checkout(plan, "flutterwave")}>
                        {busy === `${plan.code}:flutterwave` ? "Redirecting…" : "Mobile money / local card"}
                      </Button>
                    ) : null}
                  </>
                ) : (
                  <Button className="w-full" disabled>
                    Payments opening soon
                  </Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

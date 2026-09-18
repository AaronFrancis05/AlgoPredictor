"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { Disclaimer, PickCard } from "@/components/picks";
import { Alert, Button, Card, Field, Input, PageHeader } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { isoDate, odds, pct } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { Slip, SlipForm, type SlipFormInput, type SlipFormOutput } from "@/lib/schemas";

export default function SlipBuilder() {
  const me = useMe();
  const canValue = Boolean(me.data?.entitlements.value_flags);
  const { register, handleSubmit, formState } = useForm<SlipFormInput, unknown, SlipFormOutput>({
    resolver: zodResolver(SlipForm),
    defaultValues: { target_odds: 10, min_legs: 2, max_legs: 5, days_ahead: 3, prefer_value: false },
  });
  const e = formState.errors;

  const build = useMutation({
    mutationFn: (v: SlipFormOutput) => {
      const from = new Date();
      const to = new Date();
      to.setUTCDate(to.getUTCDate() + v.days_ahead);
      return api("/slips", Slip, {
        method: "POST",
        json: { target_odds: v.target_odds, min_legs: v.min_legs, max_legs: v.max_legs,
                date_from: isoDate(from), date_to: isoDate(to), prefer_value: canValue && v.prefer_value },
      });
    },
  });

  const slip = build.data;
  return (
    <>
      <PageHeader
        title="Slip builder"
        subtitle="Enter the total odds you want. We search upcoming picks for the combination most likely to land."
      />
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card className="h-fit">
          <form onSubmit={handleSubmit((v) => build.mutate(v))} noValidate className="space-y-4">
            <Field label="Target odds" htmlFor="target_odds" error={e.target_odds?.message} hint="Between 1.5 and 200">
              <Input id="target_odds" type="number" step="0.1" inputMode="decimal" {...register("target_odds")} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Min legs" htmlFor="min_legs" error={e.min_legs?.message}>
                <Input id="min_legs" type="number" min={2} max={6} {...register("min_legs")} />
              </Field>
              <Field label="Max legs" htmlFor="max_legs" error={e.max_legs?.message}>
                <Input id="max_legs" type="number" min={2} max={6} {...register("max_legs")} />
              </Field>
            </div>
            <Field label="Look ahead (days)" htmlFor="days_ahead" error={e.days_ahead?.message}>
              <Input id="days_ahead" type="number" min={0} max={14} {...register("days_ahead")} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" disabled={!canValue} {...register("prefer_value")} />
              Prefer VALUE legs {canValue ? "" : "(Elite)"}
            </label>
            <Button type="submit" className="w-full" disabled={build.isPending}>
              {build.isPending ? "Searching…" : "Build slip"}
            </Button>
            <p className="text-xs text-muted">One leg per match, odds 1.20–2.50, matches not yet started.</p>
          </form>
        </Card>

        <div className="space-y-4">
          {build.error ? <ErrorPanel error={build.error} /> : null}
          {slip ? (
            slip.found ? (
              <>
                <Card className="grid gap-4 sm:grid-cols-4">
                  <div><p className="text-xs text-muted">Target</p><p className="text-2xl font-bold tabular-nums">{odds(slip.target_odds)}</p></div>
                  <div><p className="text-xs text-muted">Combined odds</p><p className="text-2xl font-bold tabular-nums">{odds(slip.combined_odds)}</p></div>
                  <div><p className="text-xs text-muted">Model win probability</p><p className="text-2xl font-bold tabular-nums">{pct(slip.combined_probability)}</p></div>
                  <div><p className="text-xs text-muted">Expected value</p><p className="text-2xl font-bold tabular-nums">{slip.expected_value != null ? `${(slip.expected_value * 100).toFixed(1)}%` : "—"}</p></div>
                </Card>
                <Alert>{slip.message}</Alert>
                {slip.remaining_today != null ? <p className="text-xs text-muted">{slip.remaining_today} slip(s) left today.</p> : null}
                <div className="grid gap-4 md:grid-cols-2">
                  {slip.legs.map((p) => <PickCard key={p.prediction_id} pick={p} showValue={canValue} />)}
                </div>
              </>
            ) : (
              <Alert tone="warn">{slip.message}</Alert>
            )
          ) : !build.error ? (
            <Card className="text-sm text-muted">Your slip appears here. Higher targets need more legs and win far less often.</Card>
          ) : null}
          <Disclaimer />
        </div>
      </div>
    </>
  );
}

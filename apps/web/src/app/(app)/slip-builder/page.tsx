"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueries } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";

import { Disclaimer, KickoffTime, leagueName, TierBadge } from "@/components/picks";
import { Alert, Badge, Button, Card, Field, Input, PageHeader } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { isoDate, odds, pct, pickLabel, prob, today } from "@/lib/format";
import { useMe, useNow } from "@/lib/hooks";
import { picksQuery } from "@/lib/queries";
import { type Pick, Slip, SlipForm, type SlipFormInput, type SlipFormOutput } from "@/lib/schemas";
import { candidates, legProblem, MAX_LEGS, ODDS_MAX, ODDS_MIN, slipTotals } from "@/lib/slip";

const MAX_CANDIDATE_DAYS = 7; // days of picks offered for manual legs (one cached request per day)
const SHOWN_CANDIDATES = 15;

function addDays(day: string, n: number) {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return isoDate(d);
}

function LegRow({ pick, action }: { pick: Pick; action: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 bg-surface px-4 py-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{pick.home_team} <span className="text-muted">v</span> {pick.away_team}</p>
        <p className="truncate text-xs text-muted">
          <KickoffTime iso={pick.kickoff_at} /> · {leagueName(pick.league_code)}
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
          <strong className="text-sm">{pickLabel(pick.pick, pick.home_team, pick.away_team)}</strong>
          <span className="num text-muted">odds {odds(pick.odds)} · p {prob(pick.confidence)}</span>
          <TierBadge tier={pick.tier} />
        </p>
      </div>
      {action}
    </li>
  );
}

export default function SlipBuilder() {
  const me = useMe();
  const now = useNow(30_000);
  const canValue = Boolean(me.data?.entitlements.value_flags);
  const { register, handleSubmit, formState, control } = useForm<SlipFormInput, unknown, SlipFormOutput>({
    resolver: zodResolver(SlipForm),
    defaultValues: { target_odds: 10, min_legs: 2, max_legs: 5, days_ahead: 3, prefer_value: false },
  });
  const e = formState.errors;
  const [watchedDays, watchedTarget] = useWatch({ control, name: ["days_ahead", "target_odds"] });
  const [legs, setLegs] = useState<Pick[]>([]);
  const [built, setBuilt] = useState<Slip | null>(null);

  const build = useMutation({
    mutationFn: (v: SlipFormOutput) => {
      const from = today(); // the viewer's date, like every other page
      return api("/slips", Slip, {
        method: "POST",
        json: { target_odds: v.target_odds, min_legs: v.min_legs, max_legs: v.max_legs,
                date_from: from, date_to: addDays(from, v.days_ahead), prefer_value: canValue && v.prefer_value },
      });
    },
    onSuccess: (s) => { setBuilt(s); setLegs(s.found ? s.legs : []); },
  });

  // picks for the look-ahead window, offered as manual legs (same cached queries as the Today page)
  const daysAhead = Math.min(MAX_CANDIDATE_DAYS - 1, Math.max(0, Number(watchedDays) || 0));
  const days = useMemo(() => Array.from({ length: daysAhead + 1 }, (_, i) => addDays(today(), i)), [daysAhead]);
  const pools = useQueries({ queries: days.map((d) => picksQuery(d)) });
  const pool = useMemo(() => pools.flatMap((q) => q.data?.picks ?? []), [pools]);
  const offer = useMemo(() => candidates(pool, legs, now).slice(0, SHOWN_CANDIDATES), [pool, legs, now]);

  const totals = slipTotals(legs);
  const target = Number(watchedTarget) || null;
  const edited = built?.found === true
    && legs.map((l) => l.prediction_id).join() !== built.legs.map((l) => l.prediction_id).join();
  // a leg can kick off while the slip is open: flag it rather than silently dropping it
  const stale = legs.filter((l) => Date.parse(l.kickoff_at) <= now);

  return (
    <>
      <PageHeader
        title="Slip builder"
        subtitle="Enter the total odds you want and we search upcoming picks for the combination most likely to land. Then add, remove or swap legs yourself."
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
            <p className="text-xs text-muted">
              One leg per match, odds {ODDS_MIN.toFixed(2)}–{ODDS_MAX.toFixed(2)}, matches not yet started.
              Editing a slip below does not use your daily allowance.
            </p>
          </form>
        </Card>

        <div className="space-y-4">
          {build.error ? <ErrorPanel error={build.error} /> : null}
          {built && !built.found ? <Alert tone="warn">{built.message}</Alert> : null}
          {built?.remaining_today != null ? <p className="text-xs text-muted">{built.remaining_today} slip search(es) left today.</p> : null}

          <Card className="grid gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs text-muted">Target</p>
              <p className="num text-2xl font-bold">{target ? odds(target) : "n/a"}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Combined odds</p>
              <p className="num text-2xl font-bold">{totals ? odds(totals.odds) : "n/a"}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Model win probability</p>
              <p className="num text-2xl font-bold">{totals ? pct(totals.probability) : "n/a"}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Expected value</p>
              <p className="num text-2xl font-bold">{totals ? `${(totals.expectedValue * 100).toFixed(1)}%` : "n/a"}</p>
            </div>
          </Card>
          <p className="text-xs text-muted">
            Combined probability multiplies the model&apos;s leg probabilities and assumes the matches are independent.
            It is an estimate, not a guarantee. Each extra leg adds another bookmaker margin.
          </p>

          <section className="space-y-3" aria-labelledby="legs">
            <div className="flex items-center justify-between gap-3">
              <h2 id="legs" className="text-sm font-semibold">
                Your slip <span className="num font-normal text-muted">{legs.length}/{MAX_LEGS}</span>
                {edited ? <Badge className="ml-2">Edited</Badge> : null}
              </h2>
              <div className="flex gap-2">
                {edited && built ? (
                  <Button variant="secondary" className="px-2.5 py-1.5 text-xs" onClick={() => setLegs(built.legs)}>
                    Undo edits
                  </Button>
                ) : null}
                {legs.length ? (
                  <Button variant="secondary" className="px-2.5 py-1.5 text-xs" onClick={() => setLegs([])}>Clear</Button>
                ) : null}
              </div>
            </div>
            {stale.length ? (
              <Alert tone="warn">
                {stale.length === 1 ? "One leg has" : `${stale.length} legs have`} already kicked off. Remove
                {stale.length === 1 ? " it" : " them"} before placing the slip.
              </Alert>
            ) : null}
            {legs.length ? (
              <ul className="divide-y divide-border overflow-hidden rounded-card border border-border">
                {legs.map((l) => (
                  <LegRow key={l.prediction_id} pick={l} action={
                    <Button variant="secondary" className="px-2" aria-label={`Remove ${l.home_team} v ${l.away_team}`}
                            onClick={() => setLegs(legs.filter((x) => x.prediction_id !== l.prediction_id))}>
                      <X className="h-4 w-4" aria-hidden />
                    </Button>
                  } />
                ))}
              </ul>
            ) : (
              <Card className="text-sm text-muted">
                Build a slip with the form, or add legs yourself from the list below. Higher targets need more legs
                and win far less often.
              </Card>
            )}
          </section>

          <section className="space-y-3" aria-labelledby="add-legs">
            <h2 id="add-legs" className="text-sm font-semibold">
              Add a leg <span className="font-normal text-muted">(next {days.length} day{days.length === 1 ? "" : "s"}, most likely first)</span>
            </h2>
            {legs.length >= MAX_LEGS ? (
              <p className="text-xs text-muted">The slip is full. Remove a leg to add another.</p>
            ) : offer.length ? (
              <ul className="divide-y divide-border overflow-hidden rounded-card border border-border">
                {offer.map((p) => (
                  <LegRow key={p.prediction_id} pick={p} action={
                    <Button variant="secondary" className="px-2" aria-label={`Add ${p.home_team} v ${p.away_team}`}
                            disabled={legProblem(p, legs, now) != null} onClick={() => setLegs([...legs, p])}>
                      <Plus className="h-4 w-4" aria-hidden />
                    </Button>
                  } />
                ))}
              </ul>
            ) : pools.some((q) => q.isLoading) ? (
              <p className="text-xs text-muted">Loading picks…</p>
            ) : (
              <p className="text-xs text-muted">No other upcoming picks fit the leg rules in this window.</p>
            )}
          </section>
          <Disclaimer />
        </div>
      </div>
    </>
  );
}

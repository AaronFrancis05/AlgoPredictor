import { Lock } from "lucide-react";

import { Badge, Card } from "@/components/ui";
import { cn, kickoff, odds, pct, pickLabel, prob } from "@/lib/format";
import type { Pick } from "@/lib/schemas";
import { leagueNames } from "@/lib/site";

const tierStyle: Record<string, string> = {
  Strong: "border-strong/50 bg-strong/15 text-strong",
  Medium: "border-medium/50 bg-medium/15 text-medium",
  Lean: "border-lean/50 bg-lean/15 text-lean",
  locked: "border-border text-muted",
};

export function TierBadge({ tier, hitRate }: { tier: string; hitRate?: number | null }) {
  return (
    <Badge
      className={tierStyle[tier] ?? tierStyle.locked}
      title={hitRate != null ? `${tier}: ${pct(hitRate)} of past picks in this tier won` : undefined}
    >
      {tier === "locked" ? "Locked" : tier}
    </Badge>
  );
}

/** Home / draw / away probabilities as one accessible bar. */
export function ProbabilityBar({ pick }: { pick: Pick }) {
  if (pick.p_home == null || pick.p_draw == null || pick.p_away == null) return null;
  const parts = [
    { key: "home", label: "Home", v: pick.p_home, cls: "bg-accent" },
    { key: "draw", label: "Draw", v: pick.p_draw, cls: "bg-lean" },
    { key: "away", label: "Away", v: pick.p_away, cls: "bg-warn" },
  ];
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        {parts.map((p) => (
          <div key={p.key} className={cn(p.cls, pick.pick === p.key ? "" : "opacity-40")} style={{ width: `${p.v * 100}%` }} />
        ))}
      </div>
      <dl className="mt-1.5 grid grid-cols-3 text-xs text-muted">
        {parts.map((p) => (
          <div key={p.key} className={cn(p.key === "draw" && "text-center", p.key === "away" && "text-right")}>
            <dt className="sr-only">{p.label} probability</dt>
            <dd className={cn(pick.pick === p.key && "font-semibold text-fg")}>
              {p.label} {pct(p.v, 0)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function PickCard({ pick, showValue = false }: { pick: Pick; showValue?: boolean }) {
  const settled = pick.result != null;
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted">
            {leagueNames[pick.league_code] ?? pick.league_code} · <time dateTime={pick.kickoff_at}>{kickoff(pick.kickoff_at)}</time>
          </p>
          <h3 className="mt-1 truncate text-base font-semibold">
            {pick.home_team} <span className="text-muted">v</span> {pick.away_team}
          </h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <TierBadge tier={pick.tier} hitRate={pick.tier_hit_rate} />
          {pick.is_demo ? <Badge className="border-warn/50 text-warn">Demo data</Badge> : null}
        </div>
      </div>

      {pick.locked ? (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Lock className="h-4 w-4" aria-hidden /> Upgrade or check back closer to kick-off to see this pick.
        </p>
      ) : (
        <>
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted">Pick</p>
              <p className="text-lg font-bold">{pickLabel(pick.pick, pick.home_team, pick.away_team)}</p>
            </div>
            <div className="text-right">
              <p className="text-xs uppercase tracking-wide text-muted">Model probability</p>
              <p className="text-lg font-bold tabular-nums">{prob(pick.confidence)}</p>
            </div>
          </div>
          <ProbabilityBar pick={pick} />
          <dl className="grid grid-cols-3 gap-2 text-xs">
            <div>
              <dt className="text-muted">Fair odds</dt>
              <dd className="font-semibold tabular-nums">{odds(pick.fair_odds)}</dd>
            </div>
            <div>
              <dt className="text-muted">Market odds</dt>
              <dd className="font-semibold tabular-nums">{odds(pick.odds)}</dd>
            </div>
            <div>
              <dt className="text-muted">Tier hit rate</dt>
              <dd className="font-semibold tabular-nums">{pct(pick.tier_hit_rate, 0)}</dd>
            </div>
          </dl>
          {showValue && pick.value_flag ? (
            <Badge className="w-fit border-brand/50 bg-brand/15 text-brand">
              VALUE · edge {pick.edge != null ? `${(pick.edge * 100).toFixed(1)}%` : "—"}
            </Badge>
          ) : null}
        </>
      )}
      {settled ? (
        <p className={cn("text-xs font-semibold", pick.correct ? "text-brand" : "text-danger")}>
          Result: {pick.result} · {pick.correct ? "correct" : "missed"}
        </p>
      ) : null}
    </Card>
  );
}

export function Disclaimer({ text }: { text?: string }) {
  return (
    <p className="text-xs leading-relaxed text-muted">
      {text ??
        "Predictions are model probabilities, not certainties. Even the Strong tier loses about one match in four in historical testing. 18+ only."}{" "}
      Please gamble responsibly —{" "}
      <a className="underline" href="/responsible-gambling">
        get help
      </a>
      .
    </p>
  );
}

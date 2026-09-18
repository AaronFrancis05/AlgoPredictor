"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { z } from "zod";

import { Alert, Badge, Button, Card, EmptyState, Field, Input, PageHeader, Select, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { AccessToken, AccessTokenCreated, LiveAdmin, type LiveAdminMatch, Message } from "@/lib/schemas";

const Tokens = z.array(AccessToken);
const statusStyle: Record<AccessToken["status"], string> = {
  active: "border-brand/50 bg-brand/15 text-brand",
  expired: "border-border text-muted",
  used_up: "border-warn/50 bg-warn/10 text-warn",
  revoked: "border-danger/50 bg-danger/10 text-danger",
};
const statusLabel: Record<AccessToken["status"], string> = {
  active: "Active", expired: "Expired", used_up: "Used up", revoked: "Revoked",
};

const when = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    .format(new Date(iso));

/** Default expiry for the form: 30 days from now, as a datetime-local value in the admin's own time zone. */
function defaultExpiry(): string {
  const d = new Date(Date.now() + 30 * 86_400_000);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function CreateToken({ onCreated }: { onCreated: () => void }) {
  const [plan, setPlan] = useState<"pro" | "elite">("pro");
  const [expires, setExpires] = useState(defaultExpiry);
  const [maxUses, setMaxUses] = useState("1");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<z.infer<typeof AccessTokenCreated> | null>(null);
  const [copied, setCopied] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api("/admin/access-tokens", AccessTokenCreated, {
        method: "POST",
        json: {
          plan_code: plan,
          expires_at: new Date(expires).toISOString(),
          max_redemptions: maxUses.trim() === "" ? null : Number(maxUses),
          note,
        },
      });
      setCreated(res);
      setCopied(false);
      setNote("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the token");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Card className="space-y-4">
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" noValidate>
        <Field label="Plan" htmlFor="token-plan">
          <Select id="token-plan" className="w-full py-2.5 text-sm" value={plan} onChange={(e) => setPlan(e.target.value as "pro" | "elite")}>
            <option value="pro">Pro</option>
            <option value="elite">Elite</option>
          </Select>
        </Field>
        <Field label="Access ends" htmlFor="token-expiry" hint="Your local time">
          <Input id="token-expiry" type="datetime-local" required value={expires} onChange={(e) => setExpires(e.target.value)} />
        </Field>
        <Field label="Uses allowed" htmlFor="token-uses" hint="Empty = unlimited people">
          <Input id="token-uses" type="number" min={1} inputMode="numeric" value={maxUses} onChange={(e) => setMaxUses(e.target.value)} />
        </Field>
        <Field label="Note (optional)" htmlFor="token-note" hint="Who or what it is for">
          <Input id="token-note" maxLength={120} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <div className="sm:col-span-2 lg:col-span-4">
          <Button type="submit" disabled={busy || !expires}>
            <KeyRound className="h-4 w-4" aria-hidden />{busy ? "Creating…" : "Create token"}
          </Button>
        </div>
      </form>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {created ? (
        <div className="space-y-2 rounded-md border border-brand/40 bg-brand/10 p-4">
          <p className="text-sm font-semibold">
            Token for <span className="capitalize">{created.plan_code}</span>, valid until {when(created.expires_at)}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="num rounded-sm border border-border bg-surface px-3 py-2 text-base font-semibold tracking-wider">
              {created.code}
            </code>
            <Button type="button" variant="secondary" onClick={copy}>
              <Copy className="h-4 w-4" aria-hidden />{copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="text-xs text-muted">
            Copy it now. Only a fingerprint is stored, so it cannot be shown again. Recipients enter it under Account, Access code.
          </p>
        </div>
      ) : null}
    </Card>
  );
}

function TokenTable({ tokens, onRevoke }: { tokens: AccessToken[]; onRevoke: (t: AccessToken) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface">
      <table className="w-full min-w-[820px] text-sm">
        <thead className="border-b border-border text-left text-xs text-muted">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-medium">Code</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Plan</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">Used</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Access ends</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Note</th>
            <th scope="col" className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {tokens.map((t) => (
            <FragmentRow key={t.id} t={t} expanded={open === t.id} onToggle={() => setOpen(open === t.id ? null : t.id)}
                         onRevoke={() => onRevoke(t)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FragmentRow({ t, expanded, onToggle, onRevoke }: {
  t: AccessToken; expanded: boolean; onToggle: () => void; onRevoke: () => void;
}) {
  return (
    <>
      <tr className="align-top">
        <td className="num whitespace-nowrap px-4 py-3 font-semibold">{t.code_hint}…</td>
        <td className="px-4 py-3 capitalize">{t.plan_code}</td>
        <td className="px-4 py-3"><Badge className={statusStyle[t.status]}>{statusLabel[t.status]}</Badge></td>
        <td className="num px-4 py-3 text-right">
          {t.redemptions}{t.max_redemptions != null ? ` / ${t.max_redemptions}` : ""}
        </td>
        <td className="whitespace-nowrap px-4 py-3">{when(t.expires_at)}</td>
        <td className="max-w-[14rem] truncate px-4 py-3 text-muted" title={t.note}>{t.note || "n/a"}</td>
        <td className="whitespace-nowrap px-4 py-3 text-right">
          <div className="flex justify-end gap-2">
            {t.redemptions > 0 ? (
              <Button variant="ghost" className="px-2.5 py-1.5 text-xs" aria-expanded={expanded} onClick={onToggle}>
                {expanded ? "Hide users" : "Users"}
              </Button>
            ) : null}
            {t.status !== "revoked" ? (
              <Button variant="secondary" className="px-2.5 py-1.5 text-xs text-danger" onClick={onRevoke}>Revoke</Button>
            ) : null}
          </div>
        </td>
      </tr>
      {expanded ? (
        <tr>
          <td colSpan={7} className="bg-surface-2/40 px-4 py-3">
            <ul className="space-y-1 text-xs">
              {t.redeemed_by.map((r) => (
                <li key={r.email + r.redeemed_at} className="flex flex-wrap gap-x-4">
                  <span className="font-medium">{r.email}</span>
                  <span className="text-muted">redeemed {when(r.redeemed_at)}</span>
                  <span className={cn(r.status === "active" ? "text-brand" : "text-muted")}>{r.status}</span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      ) : null}
    </>
  );
}

const shortWhen = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));

function LinkRow({ m, onDone }: { m: LiveAdminMatch; onDone: (msg: string, ok: boolean) => void }) {
  const [choice, setChoice] = useState(m.fixture_id != null ? String(m.fixture_id) : "");
  const [busy, setBusy] = useState(false);
  async function save(fixtureId: number | null) {
    setBusy(true);
    try {
      const res = await api("/admin/livescores/link", Message, { method: "POST", json: { match_key: m.match_key, fixture_id: fixtureId } });
      onDone(res.message, true);
    } catch (err) {
      onDone(err instanceof Error ? err.message : "Could not save the link", false);
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="grid gap-3 bg-surface px-4 py-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto] md:items-center">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{m.home_team} <span className="text-muted">v</span> {m.away_team}</p>
        <p className="text-xs text-muted">{shortWhen(m.kickoff_at)} · {m.league_code}</p>
      </div>
      <Select aria-label={`Feed fixture for ${m.home_team} v ${m.away_team}`} className="w-full py-2 text-sm" value={choice}
              onChange={(e) => setChoice(e.target.value)} disabled={m.candidates.length === 0}>
        <option value="">{m.candidates.length ? "Choose the same match in the feed…" : "No feed fixture at this kick-off"}</option>
        {m.candidates.map((c) => (
          <option key={c.id} value={c.id}>{c.home} v {c.away} · {c.league}, {c.country} · {shortWhen(c.kickoff_at)}</option>
        ))}
      </Select>
      <div className="flex gap-2">
        <Button className="px-3 py-2 text-xs" disabled={busy || !choice || Number(choice) === m.fixture_id}
                onClick={() => save(Number(choice))}>
          {m.fixture_id != null ? "Confirm" : "Link"}
        </Button>
        {m.fixture_id != null ? (
          <Button variant="secondary" className="px-3 py-2 text-xs" disabled={busy} onClick={() => save(null)}>Unlink</Button>
        ) : null}
      </div>
    </li>
  );
}

function LiveScores() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "livescores"], queryFn: () => api("/admin/livescores", LiveAdmin), refetchInterval: 60_000 });
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "livescores"] });
  const done = (text: string, ok: boolean) => { setMsg({ tone: ok ? "success" : "error", text }); if (ok) void refresh(); };

  async function sync() {
    setSyncing(true);
    try {
      done((await api("/admin/livescores/sync", Message, { method: "POST" })).message, true);
    } catch (err) {
      done(err instanceof Error ? err.message : "Sync failed", false);
    } finally {
      setSyncing(false);
    }
  }

  if (q.isLoading) return <Skeleton className="h-32 w-full" />;
  if (q.error || !q.data) return <Alert tone="error">{q.error?.message ?? "Could not load the live-score status"}</Alert>;
  const d = q.data;
  if (!d.configured) {
    return (
      <Alert tone="warn">
        No live-score feed is configured. Matches still move to Live at kick-off and to History afterwards, without scores.
        Set <code>API_FOOTBALL_KEY</code> on the Railway api and worker services to switch live scores on.
      </Alert>
    );
  }
  const cells = [
    { label: "Requests left today", value: `${d.calls_left} / ${d.budget}` },
    { label: "Provider says left", value: d.provider_remaining ?? "n/a" },
    { label: "Poll interval", value: d.poll_interval_seconds ? `${Math.round(Number(d.poll_interval_seconds) / 60 * 10) / 10} min` : "idle" },
    { label: "Last poll", value: d.last_poll ? shortWhen(d.last_poll) : "never" },
    { label: "Matches linked", value: `${d.linked} / ${d.tracked}` },
  ];
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-border bg-border sm:grid-cols-5">
        {cells.map((c) => (
          <div key={c.label} className="bg-surface px-4 py-3 last:col-span-2 sm:last:col-span-1">
            <dt className="text-xs text-muted">{c.label}</dt>
            <dd className="num mt-1 text-lg font-semibold">{c.value}</dd>
          </div>
        ))}
      </dl>
      {d.paused || d.last_error ? (
        <Alert tone={d.paused ? "error" : "warn"}>
          {d.paused ? "Feed paused for up to an hour after a provider error. " : ""}Last error: {d.last_error ?? "n/a"}
        </Alert>
      ) : null}
      {msg ? <Alert tone={msg.tone}>{msg.text}</Alert> : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Matches are linked automatically when both team names agree. Pick the rest by hand; the names are remembered.
        </p>
        <Button variant="secondary" disabled={syncing} onClick={sync}>{syncing ? "Fetching…" : "Fetch fixture lists now"}</Button>
      </div>
      {d.unmatched.length ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Needs a match <span className="num font-normal text-muted">{d.unmatched.length}</span></h3>
          <ul className="divide-y divide-border overflow-hidden rounded-card border border-border">
            {d.unmatched.map((m) => <LinkRow key={m.match_key} m={m} onDone={done} />)}
          </ul>
        </div>
      ) : <p className="text-sm text-muted">Every tracked match is linked.</p>}
      {d.to_review.length ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Linked on one team name, please check <span className="num font-normal text-muted">{d.to_review.length}</span></h3>
          <ul className="divide-y divide-border overflow-hidden rounded-card border border-border">
            {d.to_review.map((m) => <LinkRow key={m.match_key} m={m} onDone={done} />)}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Roles() {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "user">("admin");
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const qc = useQueryClient();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const res = await api("/admin/users/role", Message, { method: "POST", json: { email, role } });
      setMsg({ tone: "success", text: res.message });
      setEmail("");
      await qc.invalidateQueries({ queryKey: ["me"] });
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof Error ? err.message : "Could not change the role" });
    }
  }

  return (
    <Card className="space-y-4">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <Field label="Account email" htmlFor="role-email">
            <Input id="role-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
        </div>
        <Field label="Role" htmlFor="role-value">
          <Select id="role-value" className="py-2.5 text-sm" value={role} onChange={(e) => setRole(e.target.value as "admin" | "user")}>
            <option value="admin">Admin</option>
            <option value="user">User</option>
          </Select>
        </Field>
        <Button type="submit" disabled={!email}>Save role</Button>
      </form>
      <p className="text-xs text-muted">Admins get every feature without paying and can manage tokens and roles. There is always at least one admin.</p>
      {msg ? <Alert tone={msg.tone}>{msg.text}</Alert> : null}
    </Card>
  );
}

export default function Admin() {
  const me = useMe();
  const qc = useQueryClient();
  const isAdmin = Boolean(me.data?.is_admin);
  const q = useQuery({ queryKey: ["admin", "tokens"], queryFn: () => api("/admin/access-tokens", Tokens), enabled: isAdmin });
  const [msg, setMsg] = useState<string | null>(null);

  if (!isAdmin) {
    return <EmptyState title="Admins only">This page is for AlgoPredict administrators.</EmptyState>;
  }

  async function revoke(t: AccessToken) {
    const users = t.redemptions === 1 ? "1 person" : `${t.redemptions} people`;
    if (!window.confirm(`Revoke ${t.code_hint}…? ${users} will lose ${t.plan_code} access immediately.`)) return;
    setMsg(null);
    try {
      await api(`/admin/access-tokens/${t.id}/revoke`, AccessToken, { method: "POST" });
      await qc.invalidateQueries({ queryKey: ["admin", "tokens"] });
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Could not revoke the token");
    }
  }

  return (
    <div className="space-y-10">
      <PageHeader title="Admin" subtitle={
        <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-brand" aria-hidden />
          Signed in as {me.data?.email} with full access</span>
      } />

      <section className="space-y-3" aria-labelledby="create-title">
        <div>
          <h2 id="create-title" className="font-semibold">Create an access token</h2>
          <p className="text-sm text-muted">Gives whoever redeems it the chosen plan until the token&apos;s end date. No payment is taken.</p>
        </div>
        <CreateToken onCreated={() => qc.invalidateQueries({ queryKey: ["admin", "tokens"] })} />
      </section>

      <section className="space-y-3" aria-labelledby="tokens-title">
        <h2 id="tokens-title" className="font-semibold">
          Tokens {q.data ? <span className="num font-normal text-muted">{q.data.length}</span> : null}
        </h2>
        {msg ? <Alert tone="error">{msg}</Alert> : null}
        {q.isLoading ? <Skeleton className="h-40 w-full" /> : null}
        {q.error ? <Alert tone="error">{q.error.message}</Alert> : null}
        {q.data && q.data.length === 0 ? <EmptyState title="No tokens yet">Tokens you create appear here.</EmptyState> : null}
        {q.data && q.data.length > 0 ? <TokenTable tokens={q.data} onRevoke={revoke} /> : null}
      </section>

      <section className="space-y-3" aria-labelledby="live-title">
        <div>
          <h2 id="live-title" className="font-semibold">Live scores</h2>
          <p className="text-sm text-muted">Feed health, today&apos;s request budget, and matches the feed could not match on its own.</p>
        </div>
        <LiveScores />
      </section>

      <section className="space-y-3" aria-labelledby="roles-title">
        <div>
          <h2 id="roles-title" className="font-semibold">Roles</h2>
          <p className="text-sm text-muted">The account must exist already.</p>
        </div>
        <Roles />
      </section>
    </div>
  );
}

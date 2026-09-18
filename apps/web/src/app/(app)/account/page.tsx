"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Check, Download, KeyRound, LogOut, Minus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, Suspense, useState } from "react";
import { z } from "zod";

import { Alert, Badge, Button, ButtonLink, Card, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, initials } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { type Entitlements, Message } from "@/lib/schemas";
import { site } from "@/lib/site";

import { SignInMethods } from "./sign-in-methods";

const ApiKey = z.object({ api_key: z.string(), note: z.string() });

function Section({ id, title, description, children, tone }: {
  id: string; title: string; description: ReactNode; children: ReactNode; tone?: "danger";
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="grid gap-4 border-t border-border py-8 md:grid-cols-[15rem_1fr] md:gap-10">
      <div>
        <h2 id={`${id}-title`} className={cn("font-semibold", tone === "danger" && "text-danger")}>{title}</h2>
        <div className="mt-1 text-sm leading-relaxed text-muted">{description}</div>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function entitlementRows(e: Entitlements): { label: string; value: string | boolean }[] {
  const picks = e.picks_per_day == null ? "Every pick" : `${e.picks_per_day} a day`;
  const reveal = e.reveal_hours_before_kickoff == null ? "" : `, shown ${e.reveal_hours_before_kickoff} h before kick-off`;
  return [
    { label: "Daily picks", value: picks + reveal },
    { label: "Daily top 10", value: e.top10 },
    { label: "Slip builder", value: e.slip_builder ? (e.slips_per_day == null ? "Unlimited" : `${e.slips_per_day} slips a day`) : false },
    { label: "Weekly jackpot", value: e.jackpot },
    { label: "VALUE flags", value: e.value_flags },
    { label: "API access", value: e.api_access },
  ];
}

function Included({ value }: { value: string | boolean }) {
  if (typeof value === "string") return <span className="font-medium">{value}</span>;
  return value ? (
    <span className="inline-flex items-center gap-1.5 font-medium"><Check className="h-4 w-4 text-brand" aria-hidden />Included</span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-muted"><Minus className="h-4 w-4" aria-hidden />Not included</span>
  );
}

function RedeemCode() {
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    setBusy(true);
    try {
      const res = await api("/me/access-token", Message, { method: "POST", json: { code } });
      setMsg({ tone: "success", text: res.message });
      setCode("");
      await qc.invalidateQueries();  // plan changed: every cached view may unlock
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof Error ? err.message : "Could not use the code" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-3">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="access-code-input" className="sr-only">Access code</label>
        <Input id="access-code-input" className="num uppercase tracking-wider" placeholder="AP-XXXX-XXXX-XXXX-XXXX"
               autoComplete="off" spellCheck={false} value={code} onChange={(e) => setCode(e.target.value)} />
        <Button type="submit" disabled={busy || code.trim().length < 8} className="shrink-0">
          {busy ? "Checking…" : "Use code"}
        </Button>
      </form>
      {msg ? <Alert tone={msg.tone}>{msg.text}</Alert> : null}
    </Card>
  );
}

export default function Account() {
  const me = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const [key, setKey] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState("");
  const [closing, setClosing] = useState(false);
  const user = me.data;
  if (!user) return null;
  const retentionDays = user.account_retention_days;
  const memberSince = user.created_at
    ? new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(new Date(user.created_at))
    : null;

  async function run(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    try {
      await fn();
      setMsg({ tone: "success", text: ok });
    } catch (e) {
      setMsg({ tone: "error", text: e instanceof Error ? e.message : "Action failed" });
    }
  }

  async function exportData() {
    const res = await fetch("/api/v1/me/export", { credentials: "same-origin" });
    if (!res.ok) throw new Error("Export failed");
    const blob = new Blob([JSON.stringify(await res.json(), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "algopredict-my-data.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function closeAccount() {
    setMsg(null);
    setClosing(true);
    try {
      await api("/me", Message, { method: "DELETE" });
      qc.clear();
      router.replace("/login?notice=account_closed");
    } catch (e) {
      setClosing(false);
      setMsg({ tone: "error", text: e instanceof Error ? e.message : "Could not close the account" });
    }
  }

  return (
    <div className="max-w-5xl">
      <div className="flex flex-col gap-5 pb-8 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <span className="grid h-14 w-14 shrink-0 place-items-center rounded-card bg-surface-2 text-lg font-bold">
            {initials(user.full_name, user.email)}
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold tracking-tight">{user.full_name || "Your account"}</h1>
            <p className="truncate text-sm text-muted">{user.email}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
              <Badge className="capitalize">{user.plan} plan</Badge>
              {user.is_admin ? <Badge className="border-brand/50 text-brand">Admin</Badge> : null}
              {user.email_verified ? (
                <span className="inline-flex items-center gap-1"><BadgeCheck className="h-3.5 w-3.5 text-brand" aria-hidden />Email verified</span>
              ) : (
                <span className="text-warn">Email not verified</span>
              )}
              {memberSince ? <span>Member since {memberSince}</span> : null}
            </div>
          </div>
        </div>
        {user.plan === "free" && !user.is_admin ? <ButtonLink href="/account/plans">Upgrade</ButtonLink> : null}
      </div>

      {msg ? <div className="mb-6"><Alert tone={msg.tone}>{msg.text}</Alert></div> : null}

      <Section id="plan" title="Plan" description="What your plan includes. Changes after a payment show here within a minute.">
        <Card className="p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
            <div>
              <p className="text-xs text-muted">Current plan</p>
              <p className="text-xl font-bold capitalize">{user.plan}</p>
            </div>
            {user.is_admin ? (
              <p className="text-sm text-muted">Admin account: every feature is included and nothing is billed.</p>
            ) : (
              <div className="flex gap-2">
                <ButtonLink href="/account/billing" variant="secondary">Billing</ButtonLink>
                <ButtonLink href="/account/plans" variant={user.plan === "free" ? "primary" : "secondary"}>Change plan</ButtonLink>
              </div>
            )}
          </div>
          <table className="w-full text-sm">
            <caption className="sr-only">Features of your plan</caption>
            <tbody className="divide-y divide-border">
              {entitlementRows(user.entitlements).map((r) => (
                <tr key={r.label}>
                  <th scope="row" className="w-1/2 px-5 py-2.5 text-left font-normal text-muted">{r.label}</th>
                  <td className="px-5 py-2.5"><Included value={r.value} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </Section>

      {!user.is_admin ? (
        <Section id="access-code" title="Access code"
                 description="Got a code from AlgoPredict? It unlocks a plan until the date set on the code, with no payment.">
          <RedeemCode />
        </Section>
      ) : null}

      <Section id="sign-in" title="Sign-in methods"
               description="Both methods open the same account, with the same plan and history. You always keep at least one.">
        <Suspense>
          <SignInMethods user={user} />
        </Suspense>
      </Section>

      <Section id="api" title="API access" description={<>Read picks from your own tools. Send the key in the <code className="num">X-API-Key</code> header.</>}>
        <Card className="space-y-3">
          {user.entitlements.api_access ? (
            <>
              <div className="flex items-center gap-2 text-sm">
                <KeyRound className="h-4 w-4 text-muted" aria-hidden />
                {user.has_api_key ? "A key is active. Creating a new one replaces it." : "No key yet."}
              </div>
              {key ? (
                <div className="space-y-2">
                  <Input readOnly value={key} className="num" aria-label="Your new API key" onFocus={(e) => e.currentTarget.select()} />
                  <p className="text-xs text-warn">Copy it now. It will not be shown again.</p>
                </div>
              ) : null}
              <div className="flex gap-2">
                <Button onClick={() => run(async () => {
                  const r = await api("/me/api-key", ApiKey, { method: "POST" });
                  setKey(r.api_key);
                  await qc.invalidateQueries({ queryKey: ["me"] });
                }, "New API key created.")}>{user.has_api_key ? "Replace key" : "Create key"}</Button>
                {user.has_api_key ? (
                  <Button variant="secondary" onClick={() => run(async () => {
                    await api("/me/api-key", Message, { method: "DELETE" });
                    setKey(null);
                    await qc.invalidateQueries({ queryKey: ["me"] });
                  }, "API key deleted.")}>Delete key</Button>
                ) : null}
              </div>
            </>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-muted">API access is included in the Elite plan.</p>
              <ButtonLink href="/account/plans" variant="secondary">Compare plans</ButtonLink>
            </div>
          )}
        </Card>
      </Section>

      <Section id="data" title="Security and data" description="Sign out of other devices, or take a copy of everything we hold about you.">
        <Card className="divide-y divide-border p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <div>
              <p className="text-sm font-medium">Sign out of all devices</p>
              <p className="text-xs text-muted">Ends every session, including this one.</p>
            </div>
            <Button variant="secondary" onClick={() => run(async () => {
              await api("/auth/logout-all", Message, { method: "POST" });
              qc.clear();
              router.replace("/login");
            }, "Signed out everywhere.")}><LogOut className="h-4 w-4" aria-hidden />Sign out everywhere</Button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <div>
              <p className="text-sm font-medium">Download my data</p>
              <p className="text-xs text-muted">Profile, subscriptions, payments, slips and security events, as JSON.</p>
            </div>
            <Button variant="secondary" onClick={() => run(exportData, "Your data has been downloaded.")}>
              <Download className="h-4 w-4" aria-hidden />Download
            </Button>
          </div>
        </Card>
      </Section>

      <Section id="close" title="Close account" tone="danger" description={
        <>Closing is immediate. Read what happens to your data before you go. See the <Link className="underline" href="/legal/privacy">privacy policy</Link>.</>
      }>
        <Card className="space-y-4 border-danger/40">
          <ul className="space-y-2 text-sm">
            <li>You are signed out on every device and can no longer sign in. Your API key stops working.</li>
            <li>
              {retentionDays == null
                ? "Your account data is kept for a limited retention period for legal and record-keeping purposes, then erased for good."
                : retentionDays === 0
                  ? "Your account data is erased within a day."
                  : <>Your account data is kept for <strong>{retentionDays} days</strong> for legal and record-keeping purposes, then
                      erased for good. To restore the account before then, email{" "}
                      <a className="underline" href={`mailto:${site.supportEmail}`}>{site.supportEmail}</a>.</>}
            </li>
            <li>Payment records are kept for accounting, without your name or email.</li>
            <li>Cancel any card subscription in <Link className="underline" href="/account/billing">Billing</Link> first, so you are not charged again.</li>
          </ul>
          <div className="space-y-2">
            <label htmlFor="confirm-delete" className="block text-sm">Type <strong>DELETE</strong> to confirm</label>
            <Input id="confirm-delete" value={confirmDelete} autoComplete="off" onChange={(e) => setConfirmDelete(e.target.value)} />
          </div>
          <Button variant="danger" disabled={confirmDelete !== "DELETE" || closing} onClick={closeAccount}>
            {closing ? "Closing…" : "Close my account"}
          </Button>
        </Card>
      </Section>
    </div>
  );
}

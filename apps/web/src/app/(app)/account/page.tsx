"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";

import { Alert, Button, ButtonLink, Card, Input, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { Message } from "@/lib/schemas";

const ApiKey = z.object({ api_key: z.string(), note: z.string() });

export default function Account() {
  const me = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const [key, setKey] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState("");
  const user = me.data;
  if (!user) return null;

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

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader title="Account" subtitle={user.email} />
      {msg ? <Alert tone={msg.tone}>{msg.text}</Alert> : null}

      <Card className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs text-muted">Current plan</p>
          <p className="text-xl font-bold capitalize">{user.plan}</p>
        </div>
        <div className="flex gap-2">
          <ButtonLink href="/account/billing" variant="secondary">Billing</ButtonLink>
          <ButtonLink href="/pricing">Change plan</ButtonLink>
        </div>
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">API access</h2>
        {user.entitlements.api_access ? (
          <>
            <p className="text-sm text-muted">Send your key in the <code>X-API-Key</code> header. Creating a new key replaces the old one.</p>
            {key ? (
              <div className="space-y-2">
                <Input readOnly value={key} aria-label="Your new API key" onFocus={(e) => e.currentTarget.select()} />
                <p className="text-xs text-warn">Copy it now — it will not be shown again.</p>
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
          <p className="text-sm text-muted">API access is included in the Elite plan.</p>
        )}
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">Security & data</h2>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => run(async () => {
            await api("/auth/logout-all", Message, { method: "POST" });
            qc.clear();
            router.replace("/login");
          }, "Signed out everywhere.")}>Sign out of all devices</Button>
          <Button variant="secondary" onClick={() => run(exportData, "Your data has been downloaded.")}>Download my data</Button>
        </div>
      </Card>

      <Card className="space-y-3 border-danger/40">
        <h2 className="font-semibold text-danger">Delete account</h2>
        <p className="text-sm text-muted">
          This permanently deletes your account. Cancel any card subscription in Billing first. Type <strong>DELETE</strong> to confirm.
        </p>
        <Input value={confirmDelete} onChange={(e) => setConfirmDelete(e.target.value)} aria-label="Type DELETE to confirm" />
        <Button variant="danger" disabled={confirmDelete !== "DELETE"} onClick={() => run(async () => {
          await api("/me", Message, { method: "DELETE" });
          qc.clear();
          router.replace("/");
        }, "Account deleted.")}>Delete my account</Button>
      </Card>
    </div>
  );
}

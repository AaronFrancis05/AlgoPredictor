"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Button } from "@/components/ui";
import { api } from "@/lib/api";
import { Message } from "@/lib/schemas";

/** Confirmation needs a click (not an automatic request on load), so link scanners cannot consume the token. */
export function VerifyEmail({ token }: { token: string }) {
  const [state, setState] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      const res = await api("/auth/verify-email", Message, { method: "POST", json: { token } });
      setState({ tone: "success", text: res.message });
    } catch (e) {
      setState({ tone: "error", text: e instanceof Error ? e.message : "Confirmation failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Confirm your email</h1>
      {!token ? <Alert tone="error">This link is missing its token. Use the link from your email.</Alert> : null}
      {state ? <Alert tone={state.tone}>{state.text}</Alert> : null}
      {state?.tone === "success" ? (
        <Link className="text-sm text-accent underline" href="/login">Continue to sign in</Link>
      ) : (
        <Button className="w-full" onClick={confirm} disabled={!token || busy}>
          {busy ? "Confirming…" : "Confirm my email"}
        </Button>
      )}
    </div>
  );
}

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { Message, MfaSetup, RecoveryCodes, type User } from "@/lib/schemas";

type Notice = { tone: "success" | "error"; text: string } | null;
type Mode = "idle" | "setup" | "codes" | "regenerate" | "disable";

/** Two-factor sign-in with an authenticator app (TOTP). Required for admins before they can open /admin. */
export function TwoFactor({ user }: { user: User }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("idle");
  const [notice, setNotice] = useState<Notice>(null);
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setNotice(null);
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["me"] });
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Action failed" });
    } finally {
      setBusy(false);
      setCode("");
    }
  }

  const start = () => run(async () => {
    setSetup(await api("/me/mfa/setup", MfaSetup, { method: "POST" }));
    setMode("setup");
  });

  const enable = () => run(async () => {
    const res = await api("/me/mfa/enable", RecoveryCodes, {
      method: "POST", json: { code: code.replace(/\s/g, ""), current_password: user.has_password ? password : null },
    });
    setPassword("");
    setSetup(null);
    setCodes(res.recovery_codes);
    setMode("codes");
  });

  const regenerate = () => run(async () => {
    const res = await api("/me/mfa/recovery-codes", RecoveryCodes, { method: "POST", json: { code: code.replace(/\s/g, "") } });
    setCodes(res.recovery_codes);
    setMode("codes");
  });

  const disable = () => run(async () => {
    const res = await api("/me/mfa/disable", Message, { method: "POST", json: { code: code.trim() } });
    setMode("idle");
    setNotice({ tone: "success", text: res.message });
  });

  const cancel = () => { setMode("idle"); setSetup(null); setCode(""); setPassword(""); setNotice(null); };

  return (
    <Card className="space-y-4">
      {notice ? <Alert tone={notice.tone}>{notice.text}</Alert> : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Authenticator app</p>
          <p className="text-xs text-muted">
            {user.mfa_enabled ? "On. Sign-in asks for a code from your phone." : "Off. Sign-in needs only your password or Google."}
          </p>
        </div>
        {mode === "idle" ? (
          user.mfa_enabled ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setMode("regenerate")}>New recovery codes</Button>
              <Button variant="secondary" onClick={() => setMode("disable")}>Turn off</Button>
            </div>
          ) : (
            <Button variant="secondary" onClick={start} disabled={busy}>Turn on</Button>
          )
        ) : null}
      </div>

      {user.is_admin && !user.mfa_enabled && mode === "idle" ? (
        <Alert tone="warn">Admin pages stay closed until two-factor sign-in is on.</Alert>
      ) : null}

      {mode === "setup" && setup ? (
        <div className="space-y-3 border-t border-border pt-4">
          <ol className="list-decimal space-y-2 pl-5 text-sm">
            <li>
              In Google Authenticator, Microsoft Authenticator, 1Password or a similar app, add an account and enter this
              key (on your phone you can <a className="underline" href={setup.otpauth_uri}>open it in the app</a> instead):
              <code className="num mt-1 block select-all break-all rounded-md bg-surface-2 px-3 py-2 text-sm tracking-wider">
                {setup.secret.match(/.{1,4}/g)?.join(" ")}
              </code>
            </li>
            <li>Type the 6-digit code the app shows.</li>
          </ol>
          <Field label="Code from the app" htmlFor="mfa-code">
            <Input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" className="num tracking-widest"
                   value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          {user.has_password ? (
            <Field label="Current password" htmlFor="mfa-password">
              <Input id="mfa-password" type="password" autoComplete="current-password" value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </Field>
          ) : null}
          <p className="text-xs text-muted">Turning it on signs you out on every other device.</p>
          <div className="flex gap-2">
            <Button onClick={enable} disabled={busy || code.replace(/\s/g, "").length !== 6}>Turn on</Button>
            <Button variant="ghost" onClick={cancel}>Cancel</Button>
          </div>
        </div>
      ) : null}

      {mode === "codes" ? (
        <div className="space-y-3 border-t border-border pt-4">
          <Alert tone="warn">
            Save these recovery codes now. Each one works once if you lose your phone, and they are not shown again.
          </Alert>
          <ul className="num grid grid-cols-2 gap-2 text-sm">
            {codes.map((c) => <li key={c} className="rounded-md bg-surface-2 px-3 py-1.5 text-center">{c}</li>)}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => void navigator.clipboard.writeText(codes.join("\n"))}>Copy</Button>
            <Button onClick={() => { setCodes([]); setMode("idle"); }}>I have saved them</Button>
          </div>
        </div>
      ) : null}

      {mode === "regenerate" || mode === "disable" ? (
        <div className="space-y-3 border-t border-border pt-4">
          <Field label={mode === "disable" ? "Code from the app, or a recovery code" : "Code from the app"} htmlFor="mfa-confirm">
            <Input id="mfa-confirm" autoComplete="one-time-code" className="num tracking-widest" value={code}
                   onChange={(e) => setCode(e.target.value)} />
          </Field>
          <p className="text-xs text-muted">
            {mode === "disable"
              ? "Turning it off signs you out on every other device." + (user.is_admin ? " Admin pages will close." : "")
              : "Your old recovery codes stop working."}
          </p>
          <div className="flex gap-2">
            <Button variant={mode === "disable" ? "danger" : "primary"} disabled={busy || !code.trim()}
                    onClick={mode === "disable" ? disable : regenerate}>
              {mode === "disable" ? "Turn off" : "Create new codes"}
            </Button>
            <Button variant="ghost" onClick={cancel}>Cancel</Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}


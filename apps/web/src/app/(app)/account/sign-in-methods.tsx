"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { Message, PasswordSetForm, Redirect, type User } from "@/lib/schemas";

type Notice = { tone: "success" | "error"; text: string } | null;

const googleNotices: Record<string, Notice> = {
  linked: { tone: "success", text: "Google is connected. You can sign in with either method." },
  in_use: { tone: "error", text: "That Google account already belongs to another AlgoPredict account." },
};

/** One account, two ways in: email + password and Google. Either can be added; the last one cannot be removed. */
export function SignInMethods({ user }: { user: User }) {
  const qc = useQueryClient();
  const params = useSearchParams();
  const [notice, setNotice] = useState<Notice>(googleNotices[params.get("google") ?? ""] ?? null);
  const [editing, setEditing] = useState(false);
  const { register, handleSubmit, reset, formState } = useForm<PasswordSetForm>({
    resolver: zodResolver(PasswordSetForm),
  });
  const e = formState.errors;

  async function act(fn: () => Promise<string>) {
    setNotice(null);
    try {
      setNotice({ tone: "success", text: await fn() });
      await qc.invalidateQueries({ queryKey: ["me"] });
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Action failed" });
    }
  }

  const savePassword = handleSubmit((v) =>
    act(async () => {
      const res = await api("/me/password", Message, {
        method: "POST",
        json: { password: v.password, current_password: user.has_password ? v.current_password : null },
      });
      reset();
      setEditing(false);
      return res.message;
    }),
  );

  async function connectGoogle() {
    setNotice(null);
    try {
      const { url } = await api("/me/google/link", Redirect, { method: "POST" });
      window.location.assign(url); // Google returns to /account?google=linked
    } catch (err) {
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Could not reach Google" });
    }
  }

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="font-semibold">Sign-in methods</h2>
        <p className="mt-1 text-sm text-muted">Both methods open the same account, with the same plan and history.</p>
      </div>
      {notice ? <Alert tone={notice.tone}>{notice.text}</Alert> : null}

      <div className="divide-y divide-border border-y border-border">
        <div className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div>
            <p className="text-sm font-medium">Email and password</p>
            <p className="text-xs text-muted">{user.has_password ? user.email : "Not set. You sign in with Google."}</p>
          </div>
          {!editing ? (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              {user.has_password ? "Change password" : "Add a password"}
            </Button>
          ) : null}
        </div>

        {editing ? (
          <form onSubmit={savePassword} noValidate className="space-y-3 py-4">
            {user.has_password ? (
              <Field label="Current password" htmlFor="current_password" error={e.current_password?.message}>
                <Input id="current_password" type="password" autoComplete="current-password" {...register("current_password")} />
              </Field>
            ) : null}
            <Field label="New password" htmlFor="new_password" error={e.password?.message}
                   hint="10+ characters with three of: lower case, upper case, digits, symbols">
              <Input id="new_password" type="password" autoComplete="new-password" aria-invalid={!!e.password}
                     {...register("password")} />
            </Field>
            <Field label="Repeat new password" htmlFor="confirm" error={e.confirm?.message}>
              <Input id="confirm" type="password" autoComplete="new-password" aria-invalid={!!e.confirm}
                     {...register("confirm")} />
            </Field>
            <p className="text-xs text-muted">Saving signs you out on every other device.</p>
            <div className="flex gap-2">
              <Button type="submit" disabled={formState.isSubmitting}>
                {formState.isSubmitting ? "Saving…" : "Save password"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => { reset(); setEditing(false); }}>Cancel</Button>
            </div>
          </form>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div>
            <p className="text-sm font-medium">Google</p>
            <p className="text-xs text-muted">{user.google_linked ? "Connected" : "Not connected"}</p>
          </div>
          {user.google_linked ? (
            <Button
              variant="secondary"
              disabled={!user.has_password}
              title={user.has_password ? undefined : "Add a password first so you can still sign in"}
              onClick={() => act(async () => (await api("/me/google", Message, { method: "DELETE" })).message)}
            >
              Disconnect
            </Button>
          ) : (
            <Button variant="secondary" onClick={connectGoogle}>Connect Google</Button>
          )}
        </div>
      </div>
      {user.google_linked && !user.has_password ? (
        <p className="text-xs text-muted">Add a password before disconnecting Google, so you can still sign in.</p>
      ) : null}
    </Card>
  );
}

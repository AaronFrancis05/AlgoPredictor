"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { Message, ResetForm } from "@/lib/schemas";

export function ResetPassword({ token }: { token: string }) {
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof ResetForm>>({ resolver: zodResolver(ResetForm) });
  const e = formState.errors;

  const onSubmit = handleSubmit(async ({ password }) => {
    setError(null);
    try {
      setDone((await api("/auth/password/reset", Message, { method: "POST", json: { token, password } })).message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    }
  });

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Choose a new password</h1>
      {!token ? <Alert tone="error">This link is missing its token. Request a new reset email.</Alert> : null}
      {done ? <Alert tone="success">{done}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!done && token ? (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field label="New password" htmlFor="password" error={e.password?.message}>
            <Input id="password" type="password" autoComplete="new-password" {...register("password")} />
          </Field>
          <Field label="Repeat password" htmlFor="confirm" error={e.confirm?.message}>
            <Input id="confirm" type="password" autoComplete="new-password" {...register("confirm")} />
          </Field>
          <Button type="submit" className="w-full" disabled={formState.isSubmitting}>Save password</Button>
        </form>
      ) : null}
      <Link className="text-sm text-accent underline" href="/login">Sign in</Link>
    </div>
  );
}

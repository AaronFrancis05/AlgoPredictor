"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { ForgotForm, Message } from "@/lib/schemas";

export default function ForgotPasswordPage() {
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof ForgotForm>>({ resolver: zodResolver(ForgotForm) });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      setDone((await api("/auth/password/forgot", Message, { method: "POST", json: values })).message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    }
  });

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Reset your password</h1>
      {done ? <Alert tone="success">{done}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!done ? (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field label="Email" htmlFor="email" error={formState.errors.email?.message}>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
          </Field>
          <Button type="submit" className="w-full" disabled={formState.isSubmitting}>Send reset link</Button>
        </form>
      ) : null}
      <Link className="text-sm text-accent underline" href="/login">Back to sign in</Link>
    </div>
  );
}

"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { AuthResult, LoginForm as LoginSchema, type LoginForm as LoginValues } from "@/lib/schemas";

export function LoginForm({ next, initialError }: { next: string; initialError: string | null }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(initialError);
  const { register, handleSubmit, formState } = useForm<LoginValues>({ resolver: zodResolver(LoginSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      const res = await api("/auth/login", AuthResult, { method: "POST", json: values });
      qc.setQueryData(["me"], res.user);
      router.push(res.user.age_confirmed ? next : "/onboarding");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    }
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Sign in</h1>
        <p className="mt-1 text-sm text-muted">
          New here? <Link className="text-accent underline" href="/register">Create a free account</Link>
        </p>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Field label="Email" htmlFor="email" error={formState.errors.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!formState.errors.email}
                 aria-describedby="email-error" {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={formState.errors.password?.message}>
          <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!formState.errors.password}
                 aria-describedby="password-error" {...register("password")} />
        </Field>
        <div className="flex justify-end">
          <Link className="text-xs text-muted underline" href="/forgot-password">Forgot password?</Link>
        </div>
        <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <div className="relative text-center text-xs text-muted">
        <span className="bg-surface px-2">or</span>
      </div>
      {/* full navigation (not fetch): the API redirects to Google and back */}
      <a href="/api/v1/auth/google/start"
         className="inline-flex w-full items-center justify-center rounded-xl border border-border bg-surface-2 px-4 py-2.5 text-sm font-semibold hover:border-muted">
        Continue with Google
      </a>
    </div>
  );
}

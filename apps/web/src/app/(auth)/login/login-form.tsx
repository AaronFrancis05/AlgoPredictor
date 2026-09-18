"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { GoogleButton, OrDivider } from "@/components/google-button";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import {
  AuthResult,
  LoginForm as LoginSchema,
  LoginResult,
  MfaCodeForm,
  type LoginForm as LoginValues,
  type User,
} from "@/lib/schemas";

export function LoginForm({ next, initialError, notice = null, mfaPending = false }: {
  next: string; initialError: string | null; notice?: string | null; mfaPending?: boolean;
}) {
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(initialError);
  // "mfa": the password (or Google) was accepted and the account has two-factor on
  const [step, setStep] = useState<"password" | "mfa">(mfaPending ? "mfa" : "password");

  function signedIn(user: User) {
    qc.setQueryData(["me"], user);
    router.push(user.age_confirmed ? next : "/onboarding");
    router.refresh();
  }

  return step === "password" ? (
    <PasswordStep notice={notice} error={error} setError={setError}
                  onDone={(res) => ("mfa_required" in res ? setStep("mfa") : signedIn(res.user))} />
  ) : (
    <CodeStep error={error} setError={setError} onDone={(user) => signedIn(user)}
              onRestart={() => { setStep("password"); router.replace("/login"); }} />
  );
}

function PasswordStep({ notice, error, setError, onDone }: {
  notice: string | null; error: string | null; setError: (e: string | null) => void;
  onDone: (res: LoginResult) => void;
}) {
  const { register, handleSubmit, formState } = useForm<LoginValues>({ resolver: zodResolver(LoginSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      onDone(await api("/auth/login", LoginResult, { method: "POST", json: values }));
    } catch (e) {
      const message = e instanceof Error ? e.message : "Sign-in failed";
      // accounts created with Google have no password until one is added, so say how to get in
      setError(message.startsWith("Incorrect email or password")
        ? `${message}. If you signed up with Google, use Continue with Google, or reset your password to add one.`
        : message);
    }
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Sign in</h1>
        <p className="mt-1 text-sm text-muted">
          New here? <Link className="text-fg underline underline-offset-4" href="/register">Create a free account</Link>
        </p>
      </div>
      {notice && !error ? <Alert tone="success">{notice}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <GoogleButton />
      <OrDivider label="or sign in with email" />
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
    </div>
  );
}

function CodeStep({ error, setError, onDone, onRestart }: {
  error: string | null; setError: (e: string | null) => void; onDone: (user: User) => void; onRestart: () => void;
}) {
  const { register, handleSubmit, formState, reset } = useForm<MfaCodeForm>({ resolver: zodResolver(MfaCodeForm) });

  const onSubmit = handleSubmit(async ({ code }) => {
    setError(null);
    try {
      const res = await api("/auth/mfa/verify", AuthResult, { method: "POST", json: { code: code.replace(/\s/g, "") } });
      onDone(res.user);
    } catch (e) {
      reset();
      if (e instanceof ApiError && e.code === "mfa_expired") {
        onRestart();
      }
      setError(e instanceof Error ? e.message : "Sign-in failed");
    }
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Enter your code</h1>
        <p className="mt-1 text-sm text-muted">Open your authenticator app and type the 6-digit code for AlgoPredict.</p>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Field label="Authenticator code" htmlFor="code" error={formState.errors.code?.message}
               hint="Lost your phone? Enter one of your recovery codes instead.">
          <Input id="code" autoFocus inputMode="text" autoComplete="one-time-code" spellCheck={false}
                 aria-invalid={!!formState.errors.code} aria-describedby="code-error" className="num tracking-widest"
                 {...register("code")} />
        </Field>
        <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Checking…" : "Verify and sign in"}
        </Button>
        <button type="button" className="w-full text-center text-xs text-muted underline" onClick={onRestart}>
          Start again with my password
        </button>
      </form>
    </div>
  );
}

"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { GoogleButton, OrDivider } from "@/components/google-button";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { Message, RegisterForm as RegisterSchema } from "@/lib/schemas";

type In = z.input<typeof RegisterSchema>;
type Out = z.output<typeof RegisterSchema>;

export function RegisterForm() {
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<In, unknown, Out>({ resolver: zodResolver(RegisterSchema) });
  const e = formState.errors;

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      const res = await api("/auth/register", Message, {
        method: "POST",
        json: { ...values, country: values.country ? values.country.toUpperCase() : null },
      });
      setDone(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
  });

  if (done) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Check your inbox</h1>
        <Alert tone="success">{done}</Alert>
        <p className="text-sm text-muted">Click the link in the email to confirm your address, then sign in.</p>
        <Link className="text-sm text-fg underline underline-offset-4" href="/login">Go to sign in</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Create your free account</h1>
        <p className="mt-1 text-sm text-muted">
          Already registered? <Link className="text-fg underline underline-offset-4" href="/login">Sign in</Link>
        </p>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="space-y-2">
        <GoogleButton label="Sign up with Google" />
        <p className="text-xs text-muted">
          By continuing with Google you accept the <Link className="underline" href="/legal/terms">terms</Link> and{" "}
          <Link className="underline" href="/legal/privacy">privacy policy</Link>. You confirm your age on the next step.
        </p>
      </div>
      <OrDivider label="or sign up with email" />
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Field label="Name (optional)" htmlFor="full_name" error={e.full_name?.message}>
          <Input id="full_name" autoComplete="name" {...register("full_name")} />
        </Field>
        <Field label="Email" htmlFor="email" error={e.email?.message}>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!e.email} {...register("email")} />
        </Field>
        <Field label="Password" htmlFor="password" error={e.password?.message}
               hint="10+ characters with three of: lower case, upper case, digits, symbols">
          <Input id="password" type="password" autoComplete="new-password" aria-invalid={!!e.password}
                 {...register("password")} />
        </Field>
        <Field label="Country code (optional)" htmlFor="country" error={e.country?.message} hint="e.g. UG, KE, GB">
          <Input id="country" maxLength={2} autoComplete="country" {...register("country")} />
        </Field>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" {...register("confirm_age_18")} />
          <span>I confirm I am 18 or older and allowed to use betting information where I live.</span>
        </label>
        {e.confirm_age_18 ? <p role="alert" className="text-xs text-danger">{e.confirm_age_18.message}</p> : null}
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" {...register("accept_terms")} />
          <span>
            I accept the <Link className="underline" href="/legal/terms">terms</Link> and{" "}
            <Link className="underline" href="/legal/privacy">privacy policy</Link>, and understand predictions are not guaranteed.
          </span>
        </label>
        {e.accept_terms ? <p role="alert" className="text-xs text-danger">{e.accept_terms.message}</p> : null}
        <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
          {formState.isSubmitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
    </div>
  );
}

import type { Metadata } from "next";

import { safeNextPath } from "@/lib/safe-next";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const sp = await searchParams;
  const next = safeNextPath(sp.next);
  // Google accepted the account but it has two-factor on: ask for the authenticator code next
  const mfaPending = sp.mfa === "1";
  const errors: Record<string, string> = {
    google: "Google sign-in did not complete. Please try again.",
    google_unavailable: "Google sign-in is not available yet. Please use your email and password.",
  };
  const error = typeof sp.error === "string" ? (errors[sp.error] ?? null) : null;
  const notices: Record<string, string> = {
    account_closed: "Your account is closed and you have been signed out on every device.",
  };
  const notice = typeof sp.notice === "string" ? (notices[sp.notice] ?? null) : null;
  return <LoginForm next={next} initialError={error} notice={notice} mfaPending={mfaPending} />;
}

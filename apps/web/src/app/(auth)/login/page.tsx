import type { Metadata } from "next";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const sp = await searchParams;
  const next = typeof sp.next === "string" && sp.next.startsWith("/") && !sp.next.startsWith("//") ? sp.next : "/dashboard";
  const errors: Record<string, string> = {
    google: "Google sign-in did not complete. Please try again.",
    google_unavailable: "Google sign-in is not available yet. Please use your email and password.",
  };
  const error = typeof sp.error === "string" ? (errors[sp.error] ?? null) : null;
  return <LoginForm next={next} initialError={error} />;
}

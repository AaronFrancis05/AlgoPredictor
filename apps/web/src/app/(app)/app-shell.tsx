"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Logo } from "@/components/site-chrome";
import { Alert, Badge, Button, Container, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { Message } from "@/lib/schemas";
import { appNav } from "@/lib/site";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [me.error, pathname, router]);

  async function logout() {
    await api("/auth/logout", Message, { method: "POST" }).catch(() => null);
    qc.clear();
    router.replace("/");
  }

  const user = me.data;
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur">
        <Container className="flex h-16 items-center justify-between gap-4">
          <Logo />
          <div className="flex items-center gap-3">
            {user ? <Badge className="capitalize">{user.plan} plan</Badge> : null}
            <Button variant="ghost" onClick={logout}>Sign out</Button>
          </div>
        </Container>
        <Container>
          <nav aria-label="App" className="-mb-px flex gap-1 overflow-x-auto">
            {appNav.map((n) => {
              const active = pathname === n.href || pathname.startsWith(`${n.href}/`);
              return (
                <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                      className={cn("whitespace-nowrap border-b-2 px-3 py-2.5 text-sm",
                        active ? "border-brand font-semibold text-fg" : "border-transparent text-muted hover:text-fg")}>
                  {n.label}
                </Link>
              );
            })}
          </nav>
        </Container>
      </header>
      <main id="main" className="flex-1 py-8">
        <Container>
          {me.isLoading ? <Spinner /> : null}
          {user && !user.email_verified ? (
            <div className="mb-6"><Alert tone="warn">Confirm your email address to unlock predictions. Check your inbox.</Alert></div>
          ) : null}
          {user && user.email_verified && !user.age_confirmed && pathname !== "/onboarding" ? (
            <div className="mb-6"><Alert tone="warn">Please <Link className="underline" href="/onboarding">confirm you are 18+</Link> to see predictions.</Alert></div>
          ) : null}
          {user ? children : null}
        </Container>
      </main>
    </div>
  );
}

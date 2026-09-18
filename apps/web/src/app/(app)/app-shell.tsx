"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  ChevronDown,
  CreditCard,
  Layers,
  ListOrdered,
  LogOut,
  type LucideIcon,
  Receipt,
  ShieldCheck,
  Trophy,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Logo } from "@/components/site-chrome";
import { Alert, Badge, Container, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { cn, initials } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { Message, type User } from "@/lib/schemas";
import { accountNav, appNav } from "@/lib/site";

const navIcons: Record<string, LucideIcon> = {
  "/dashboard": CalendarDays,
  "/top-picks": ListOrdered,
  "/slip-builder": Layers,
  "/jackpot": Trophy,
};
const menuIcons: Record<string, LucideIcon> = {
  "/account": UserRound,
  "/account/billing": CreditCard,
  "/pricing": Receipt,
  "/track-record": ListOrdered,
  "/admin": ShieldCheck,
};

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function UserMenu({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((o) => !o)}
        className={cn("flex items-center gap-2 rounded-md border border-transparent py-1 pl-1 pr-2 hover:border-border",
          open && "border-border bg-surface")}
      >
        <span className="grid h-8 w-8 place-items-center rounded-sm bg-surface-2 text-xs font-bold">
          {initials(user.full_name, user.email)}
        </span>
        <ChevronDown className={cn("h-4 w-4 text-muted transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-full z-50 mt-2 w-64 rounded-card border border-border bg-surface text-sm">
          <div className="border-b border-border px-4 py-3">
            <p className="truncate font-semibold">{user.full_name || user.email.split("@")[0]}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
            <div className="mt-2 flex gap-1">
              <Badge className="capitalize">{user.plan} plan</Badge>
              {user.is_admin ? <Badge className="border-brand/50 text-brand">Admin</Badge> : null}
            </div>
          </div>
          <div className="py-1">
            {[...accountNav, ...(user.is_admin ? [{ href: "/admin", label: "Admin" }] : [])].map((n) => {
              const Icon = menuIcons[n.href];
              return (
                <Link key={n.href} role="menuitem" href={n.href} onClick={() => setOpen(false)}
                      className={cn("flex items-center gap-2.5 px-4 py-2 hover:bg-surface-2",
                        pathname === n.href ? "font-semibold text-fg" : "text-muted hover:text-fg")}>
                  {Icon ? <Icon className="h-4 w-4" aria-hidden /> : null}
                  {n.label}
                </Link>
              );
            })}
          </div>
          <div className="border-t border-border py-1">
            <button type="button" role="menuitem" onClick={onSignOut}
                    className="flex w-full items-center gap-2.5 px-4 py-2 text-left text-muted hover:bg-surface-2 hover:text-fg">
              <LogOut className="h-4 w-4" aria-hidden /> Sign out
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function NavLinks({ pathname, compact = false }: { pathname: string; compact?: boolean }) {
  return (
    <>
      {appNav.map((n) => {
        const Icon = navIcons[n.href];
        const active = isActive(pathname, n.href);
        return (
          <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex shrink-0 items-center gap-2 whitespace-nowrap text-sm transition-colors",
                  compact ? "px-3 py-2.5" : "h-full px-3",
                  active ? "font-semibold text-fg" : "text-muted hover:text-fg",
                )}>
            {Icon ? <Icon className={cn("h-4 w-4", active ? "text-brand" : "")} aria-hidden /> : null}
            {n.label}
            <span aria-hidden className={cn("absolute inset-x-3 bottom-0 h-0.5", active ? "bg-brand" : "bg-transparent")} />
          </Link>
        );
      })}
    </>
  );
}

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
      <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
        <Container className="flex h-16 items-center gap-6">
          <Logo />
          <nav aria-label="App" className="hidden h-full items-stretch md:flex">
            <NavLinks pathname={pathname} />
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {user ? (
              <>
                {user.plan === "free" && !user.is_admin ? (
                  <Link href="/pricing" className="hidden text-sm font-semibold text-brand hover:underline sm:inline">
                    Upgrade
                  </Link>
                ) : null}
                <Badge className={cn("hidden capitalize sm:inline-flex", user.is_admin && "border-brand/50 text-brand")}>
                  {user.is_admin ? "Admin" : user.plan}
                </Badge>
                <UserMenu user={user} onSignOut={logout} />
              </>
            ) : (
              <Skeleton className="h-8 w-14" />
            )}
          </div>
        </Container>
        <nav aria-label="App" className="scrollbar-none flex overflow-x-auto border-t border-border px-2 md:hidden">
          <NavLinks pathname={pathname} compact />
        </nav>
      </header>
      <main id="main" className="flex-1 py-8">
        <Container>
          {me.isLoading ? (
            <div className="space-y-4" aria-busy>
              <Skeleton className="h-8 w-56" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : null}
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

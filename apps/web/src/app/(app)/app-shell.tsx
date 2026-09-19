"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays,
  ChevronDown,
  CreditCard,
  Gem,
  History,
  Layers,
  LineChart,
  ListOrdered,
  LogOut,
  type LucideIcon,
  Radio,
  ShieldCheck,
  Trophy,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Logo } from "@/components/site-chrome";
import { Alert, Badge, Button, Container, Skeleton } from "@/components/ui";
import { api, ApiError, forgetSession } from "@/lib/api";
import { cn, initials } from "@/lib/format";
import { FollowsProvider, useFollows } from "@/lib/follows";
import { useLive, useMe, useNow, useToday } from "@/lib/hooks";
import { useLiveEvents } from "@/lib/live-events";
import { phaseAt } from "@/lib/match";
import { useMatchNotifications, useNotifySetting } from "@/lib/notify";
import { picksQuery } from "@/lib/queries";
import { Message, type User } from "@/lib/schemas";
import { accountNav, appNav } from "@/lib/site";

const navIcons: Record<string, LucideIcon> = {
  "/dashboard": CalendarDays,
  "/live": Radio,
  "/top-picks": ListOrdered,
  "/slip-builder": Layers,
  "/jackpot": Trophy,
  "/history": History,
};

/** Number of matches in play, for the dot on the Live tab. Shares its cache with the Live page. */
function useLiveCount(enabled: boolean): number {
  const now = useNow(30_000);
  const q = useLive(enabled);
  // same rule as the Live page: only matches still in play by the viewer's clock count
  return (q.data?.picks ?? []).filter((p) => phaseAt(p, now) === "live").length;
}

const menuIcons: Record<string, LucideIcon> = {
  "/account": UserRound,
  "/account/billing": CreditCard,
  "/account/plans": Gem,
  "/track-record": LineChart,
  "/admin": ShieldCheck,
};

function MenuLink({ href, label, active, onClick }: { href: string; label: string; active: boolean; onClick: () => void }) {
  const Icon = menuIcons[href];
  return (
    <Link role="menuitem" href={href} onClick={onClick} aria-current={active ? "page" : undefined}
          className={cn("relative flex items-center gap-2.5 px-4 py-2 hover:bg-surface-2",
            active ? "bg-surface-2 font-semibold text-fg" : "text-muted hover:text-fg")}>
      <span aria-hidden className={cn("absolute inset-y-1 left-0 w-0.5", active ? "bg-brand" : "bg-transparent")} />
      {Icon ? <Icon className={cn("h-4 w-4", active && "text-brand")} aria-hidden /> : null}
      {label}
    </Link>
  );
}

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

  const name = user.full_name || user.email.split("@")[0];
  const close = () => setOpen(false);
  const [accountLinks, otherLinks] = [accountNav.filter((n) => n.href.startsWith("/account")),
                                      accountNav.filter((n) => !n.href.startsWith("/account"))];
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
        <span className="grid h-8 w-8 place-items-center rounded-sm bg-brand text-xs font-bold text-brand-fg">
          {initials(user.full_name, user.email)}
        </span>
        <span className="hidden max-w-32 truncate text-sm font-medium md:inline">{name.split(" ")[0]}</span>
        <ChevronDown className={cn("h-4 w-4 text-muted transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-card border border-border bg-surface text-sm">
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-sm bg-brand text-sm font-bold text-brand-fg">
              {initials(user.full_name, user.email)}
            </span>
            <div className="min-w-0">
              <p className="truncate font-semibold">{name}</p>
              <p className="truncate text-xs text-muted">{user.email}</p>
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted">Plan</p>
              <p className="font-semibold capitalize">{user.is_admin ? "Admin, all features" : user.plan}</p>
            </div>
            {user.plan === "free" && !user.is_admin ? (
              <Link href="/account/plans" onClick={close}
                    className="rounded-md bg-brand px-2.5 py-1.5 text-xs font-semibold text-brand-fg hover:brightness-95">
                Upgrade
              </Link>
            ) : null}
          </div>
          <div className="py-1">
            {accountLinks.map((n) => (
              <MenuLink key={n.href} href={n.href} label={n.label} active={pathname === n.href} onClick={close} />
            ))}
          </div>
          <div className="border-t border-border py-1">
            {[...otherLinks, ...(user.is_admin ? [{ href: "/admin", label: "Admin" }] : [])].map((n) => (
              <MenuLink key={n.href} href={n.href} label={n.label} active={isActive(pathname, n.href)} onClick={close} />
            ))}
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

function NavLinks({ pathname, compact = false, liveCount = 0 }: { pathname: string; compact?: boolean; liveCount?: number }) {
  return (
    <>
      {appNav.map((n) => {
        const Icon = navIcons[n.href];
        const active = isActive(pathname, n.href);
        const showLive = n.href === "/live" && liveCount > 0;
        return (
          <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={cn(
                  "relative flex shrink-0 items-center gap-2 whitespace-nowrap text-sm transition-colors",
                  compact ? "px-3 py-2.5" : "h-full px-2.5 lg:px-3",
                  active ? "font-semibold text-fg" : "text-muted hover:text-fg",
                )}>
            {Icon ? <Icon className={cn("h-4 w-4", active ? "text-brand" : "", showLive && "text-danger")} aria-hidden /> : null}
            {n.label}
            {showLive ? (
              <span className="num rounded-sm bg-danger/15 px-1 text-[10px] font-bold text-danger" aria-label={`${liveCount} in play`}>
                {liveCount}
              </span>
            ) : null}
            <span aria-hidden className={cn("absolute inset-x-3 bottom-0 h-0.5", active ? "bg-brand" : "bg-transparent")} />
          </Link>
        );
      })}
    </>
  );
}

/** Pushed updates, and notifications for followed matches (with today's list kept loaded, as the live list drops
 * a match at full time). */
function LiveWiring({ enabled }: { enabled: boolean }) {
  const [notify] = useNotifySetting();
  const follows = useFollows();
  const today = useToday();
  useLiveEvents(enabled, enabled && notify);
  useMatchNotifications(enabled && notify, follows?.isFollowed ?? null);
  useQuery({ ...picksQuery(today), enabled: enabled && notify });
  return null;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) {
      forgetSession();
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [me.error, pathname, router]);

  async function logout() {
    await api("/auth/logout", Message, { method: "POST" }).catch(() => null);
    qc.clear();
    router.replace("/");
    router.refresh(); // drop cached signed-in page renders (staleTimes.dynamic)
  }

  const user = me.data;
  const verified = Boolean(user?.email_verified && user?.age_confirmed);
  const liveCount = useLiveCount(verified);
  return (
    <FollowsProvider enabled={verified}>
    <LiveWiring enabled={verified} />
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
        <Container className="flex h-16 items-center gap-6">
          <Logo />
          <nav aria-label="App" className="hidden h-full items-stretch lg:flex">
            <NavLinks pathname={pathname} liveCount={liveCount} />
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {user ? (
              <>
                {user.plan === "free" && !user.is_admin ? (
                  <Link href="/account/plans" className="hidden text-sm font-semibold text-brand hover:underline sm:inline">
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
        <nav aria-label="App" className="scrollbar-none flex overflow-x-auto border-t border-border px-2 lg:hidden">
          <NavLinks pathname={pathname} compact liveCount={liveCount} />
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
          {!user && me.isError && !(me.error instanceof ApiError && me.error.status === 401) ? (
            <div className="space-y-3">
              <Alert tone="error">{me.error.message}</Alert>
              <Button variant="secondary" onClick={() => void me.refetch()} disabled={me.isFetching}>
                Try again
              </Button>
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
    </FollowsProvider>
  );
}

import Link from "next/link";

import { ButtonLink, Container } from "@/components/ui";
import { nav, site } from "@/lib/site";

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-bold tracking-tight" aria-label={`${site.name} home`}>
      <span className="grid h-8 w-8 place-items-center rounded-sm bg-brand text-sm text-brand-fg">AP</span>
      <span>{site.name}</span>
    </Link>
  );
}

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur">
      <Container className="flex h-16 items-center justify-between gap-4">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-6 text-sm md:flex">
          {nav.map((n) => (
            <Link key={n.href} href={n.href} className="text-muted hover:text-fg">
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <ButtonLink href="/login" variant="ghost">
            Sign in
          </ButtonLink>
          <ButtonLink href="/register">Start free</ButtonLink>
        </div>
      </Container>
    </header>
  );
}

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-border py-10 text-sm text-muted">
      <Container className="grid gap-8 md:grid-cols-4">
        <div className="space-y-3 md:col-span-2">
          <Logo />
          <p className="max-w-sm">{site.tagline}. Probabilities, not promises.</p>
          <p className="text-xs">
            18+ only. Betting involves risk of loss. AlgoPredict sells information, not bets, and never guarantees
            results. If gambling stops being fun, <Link className="underline" href="/responsible-gambling">get help</Link>.
          </p>
        </div>
        <nav aria-label="Product" className="space-y-2">
          <p className="font-semibold text-fg">Product</p>
          <Link className="block hover:text-fg" href="/pricing">Pricing</Link>
          <Link className="block hover:text-fg" href="/how-it-works">How it works</Link>
          <Link className="block hover:text-fg" href="/track-record">Track record</Link>
        </nav>
        <nav aria-label="Legal" className="space-y-2">
          <p className="font-semibold text-fg">Legal</p>
          <Link className="block hover:text-fg" href="/legal/terms">Terms</Link>
          <Link className="block hover:text-fg" href="/legal/privacy">Privacy</Link>
          <Link className="block hover:text-fg" href="/responsible-gambling">Responsible gambling</Link>
        </nav>
      </Container>
      <Container className="mt-8 text-xs">© {year} {site.name}</Container>
    </footer>
  );
}

export const site = {
  name: "AlgoPredict",
  tagline: "Know what to back before kick-off",
  description:
    "See today's strongest football picks and how likely each one is to land. Build a slip to the odds you want in seconds, and check every past result. 18+.",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  supportEmail: "support@algopredict.app",
} as const;

export const nav = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/track-record", label: "Track record" },
  { href: "/pricing", label: "Pricing" },
] as const;

export const appNav = [
  { href: "/dashboard", label: "Today" },
  { href: "/live", label: "Live" },
  { href: "/top-picks", label: "Top 10" },
  { href: "/slip-builder", label: "Slip builder" },
  { href: "/jackpot", label: "Weekly jackpot" },
  { href: "/history", label: "History" },
] as const;

/** Signed-in user menu (Account lives here rather than among the prediction tabs). */
export const accountNav = [
  { href: "/account", label: "Account" },
  { href: "/account/billing", label: "Billing" },
  { href: "/account/plans", label: "Plans" },
  { href: "/track-record", label: "Track record" },
] as const;

export const leagueNames: Record<string, string> = {
  E0: "Premier League", E1: "Championship", E2: "League One", E3: "League Two", EC: "National League",
  SC0: "Scottish Premiership", SC1: "Scottish Championship", SC2: "Scottish League One", SC3: "Scottish League Two",
  D1: "Bundesliga", D2: "2. Bundesliga", I1: "Serie A", I2: "Serie B", SP1: "La Liga", SP2: "Segunda División",
  F1: "Ligue 1", F2: "Ligue 2", N1: "Eredivisie", B1: "Belgian Pro League", P1: "Primeira Liga", T1: "Süper Lig",
  G1: "Greek Super League",
};

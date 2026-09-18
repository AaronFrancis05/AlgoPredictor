/**
 * Zod schemas: runtime validation of API responses (mirrors apps/api/app/schemas) and of every form.
 * Types are inferred from the schemas, so there is one source of truth on the client.
 */
import { z } from "zod";

export const PickSide = z.enum(["home", "draw", "away"]);

export const MatchPhase = z.enum(["upcoming", "live", "finished", "awaiting_result", "postponed", "cancelled", "abandoned"]);
export type MatchPhase = z.infer<typeof MatchPhase>;

/** Score and status from the live-score feed (display only; the official result comes from grading). */
export const LiveScore = z.object({
  status: z.string(),
  elapsed: z.number().nullable(),
  home_goals: z.number().nullable(),
  away_goals: z.number().nullable(),
  updated_at: z.string().nullable(),
});
export type LiveScore = z.infer<typeof LiveScore>;

export const Pick = z.object({
  prediction_id: z.string(),
  kickoff_date: z.string(),
  kickoff_time: z.string(),
  kickoff_at: z.string(),
  league_code: z.string(),
  home_team: z.string(),
  away_team: z.string(),
  pick: PickSide.nullable(),
  confidence: z.number().nullable(),
  tier: z.string(),
  tier_hit_rate: z.number().nullable(),
  p_home: z.number().nullable(),
  p_draw: z.number().nullable(),
  p_away: z.number().nullable(),
  fair_odds: z.number().nullable(),
  odds: z.number().nullable(),
  edge: z.number().nullable(),
  value_flag: z.boolean().nullable(),
  locked: z.boolean(),
  is_demo: z.boolean(),
  model_version: z.string(),
  result: PickSide.nullable().optional(),
  correct: z.boolean().nullable().optional(),
  // defaults keep the site working against an API deployed before these fields existed
  phase: MatchPhase.optional().default("upcoming"),
  live: LiveScore.nullable().optional().default(null),
  outcome: z.enum(["won", "lost"]).nullable().optional().default(null),
  outcome_official: z.boolean().optional().default(false),
});
export type Pick = z.infer<typeof Pick>;

export const LivePicks = z.object({
  plan: z.string(),
  picks: z.array(Pick),
  feed: z.boolean(),
  // when the list is next expected to change (next score poll or kick-off); absent on older APIs
  next_update_at: z.string().nullable().optional().default(null),
  disclaimer: z.string(),
});
export type LivePicks = z.infer<typeof LivePicks>;

export const History = z.object({
  date_from: z.string(),
  date_to: z.string(),
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  summary: z.object({
    matches: z.number(), won: z.number(), lost: z.number(), pending: z.number(), void: z.number(),
    hit_rate: z.number().nullable(), provisional: z.number(),
  }),
  by_tier: z.array(z.object({ tier: z.string(), settled: z.number(), won: z.number(), hit_rate: z.number().nullable() })),
  leagues: z.array(z.string()),
  picks: z.array(Pick),
  disclaimer: z.string(),
});
export type History = z.infer<typeof History>;

export const LiveAdminMatch = z.object({
  match_key: z.string(),
  kickoff_at: z.string(),
  league_code: z.string(),
  home_team: z.string(),
  away_team: z.string(),
  fixture_id: z.number().nullable(),
  link_method: z.string(),
  status: z.string(),
  candidates: z.array(z.object({ id: z.number(), home: z.string(), away: z.string(), league: z.string(),
                                 country: z.string(), kickoff_at: z.string() })),
});
export type LiveAdminMatch = z.infer<typeof LiveAdminMatch>;

export const LiveAdmin = z.object({
  configured: z.boolean(),
  budget: z.number(),
  calls_left: z.number(),
  provider_remaining: z.string().nullable(),
  last_poll: z.string().nullable(),
  poll_interval_seconds: z.string().nullable(),
  last_error: z.string().nullable(),
  paused: z.boolean(),
  tracked: z.number(),
  linked: z.number(),
  unmatched: z.array(LiveAdminMatch),
  to_review: z.array(LiveAdminMatch),
});
export type LiveAdmin = z.infer<typeof LiveAdmin>;

export const PicksDay = z.object({
  date: z.string(),
  plan: z.string(),
  picks: z.array(Pick),
  total_published: z.number(),
  hidden_count: z.number(),
  tier_hit_rates: z.record(z.string(), z.number()),
  tier_hit_rates_source: z.string(),
  disclaimer: z.string(),
});
export type PicksDay = z.infer<typeof PicksDay>;

export const Slip = z.object({
  found: z.boolean(),
  target_odds: z.number(),
  combined_odds: z.number().nullable(),
  combined_probability: z.number().nullable(),
  expected_value: z.number().nullable(),
  legs: z.array(Pick),
  message: z.string(),
  remaining_today: z.number().nullable(),
});
export type Slip = z.infer<typeof Slip>;

export const Jackpot = z.object({
  week_start: z.string(),
  days: z.array(z.object({ date: z.string(), legs: z.array(Pick), combined_probability: z.number().nullable(),
                          complete: z.boolean() })),
  complete: z.boolean(),
  week_combined_probability: z.number().nullable(),
  note: z.string(),
});
export type Jackpot = z.infer<typeof Jackpot>;

export const TrackRecord = z.object({
  graded: z.number(),
  hit_rate: z.number().nullable(),
  by_tier: z.array(z.object({ tier: z.string(), graded: z.number(), hit_rate: z.number(),
                              avg_confidence: z.number() })),
  by_month: z.array(z.object({ month: z.string(), graded: z.number(), hit_rate: z.number() })),
  recent: z.array(Pick),
  live_since: z.string().nullable(),
  backtest: z.object({ matches: z.number().optional(), tier_hit_rates: z.record(z.string(), z.number()),
                       note: z.string() }),
});
export type TrackRecord = z.infer<typeof TrackRecord>;

export const Follows = z.object({ matches: z.array(z.string()), leagues: z.array(z.string()) });
export type Follows = z.infer<typeof Follows>;

export const Entitlements = z.object({
  picks_per_day: z.number().nullable(),
  reveal_hours_before_kickoff: z.number().nullable(),
  top10: z.boolean(),
  slip_builder: z.boolean(),
  slips_per_day: z.number().nullable(),
  jackpot: z.boolean(),
  value_flags: z.boolean(),
  api_access: z.boolean(),
});
export type Entitlements = z.infer<typeof Entitlements>;

export const Plan = z.object({
  code: z.enum(["free", "pro", "elite"]),
  name: z.string(),
  rank: z.number(),
  description: z.string(),
  entitlements: Entitlements,
  prices: z.array(z.object({ currency: z.string(), interval: z.enum(["month", "year"]), amount_minor: z.number(),
                             providers: z.array(z.string()) })),
});
export type Plan = z.infer<typeof Plan>;

export const User = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  country: z.string().nullable(),
  email_verified: z.boolean(),
  age_confirmed: z.boolean(),
  is_admin: z.boolean(),
  role: z.string().optional(),
  plan: z.string(),
  entitlements: Entitlements,
  has_api_key: z.boolean(),
  has_password: z.boolean(),
  google_linked: z.boolean(),
  // optional so the site keeps working against an API deployed before these fields existed
  created_at: z.string().nullable().optional(),
  account_retention_days: z.number().optional(),
  mfa_enabled: z.boolean().optional().default(false),
  mfa_session: z.boolean().optional().default(false), // this session was started with the authenticator code
});
export type User = z.infer<typeof User>;

export const AuthResult = z.object({ user: User, csrf_token: z.string(), access_token_expires_in: z.number() });
/** Password (or Google) accepted but two-factor is on: POST /auth/mfa/verify finishes signing in. */
export const MfaChallenge = z.object({ mfa_required: z.literal(true) });
export const LoginResult = z.union([AuthResult, MfaChallenge]);
export type LoginResult = z.infer<typeof LoginResult>;
export const MfaSetup = z.object({ secret: z.string(), otpauth_uri: z.string(), note: z.string() });
export type MfaSetup = z.infer<typeof MfaSetup>;
export const RecoveryCodes = z.object({ recovery_codes: z.array(z.string()), note: z.string() });

export const MfaCodeForm = z.object({
  code: z
    .string()
    .trim()
    .refine((v) => /^\d{6}$/.test(v.replace(/\s/g, "")) || /^[A-Za-z0-9]{5}-?[A-Za-z0-9]{5}$/.test(v),
            "Enter the 6-digit code, or a recovery code like ABCDE-12345"),
});
export type MfaCodeForm = z.infer<typeof MfaCodeForm>;
export const Message = z.object({ message: z.string() });
export const Redirect = z.object({ url: z.string().url() });
export const Subscription = z.object({
  plan_code: z.string(), provider: z.string(), status: z.string(), current_period_end: z.string().nullable(),
  cancel_at_period_end: z.boolean(),
});

export const AccessToken = z.object({
  id: z.string(),
  code_hint: z.string(),
  plan_code: z.string(),
  expires_at: z.string(),
  max_redemptions: z.number().nullable(),
  redemptions: z.number(),
  note: z.string(),
  status: z.enum(["active", "expired", "used_up", "revoked"]),
  created_at: z.string(),
  revoked_at: z.string().nullable(),
  redeemed_by: z.array(z.object({ email: z.string(), redeemed_at: z.string(), status: z.string() })),
});
export type AccessToken = z.infer<typeof AccessToken>;
export const AccessTokenCreated = AccessToken.extend({ code: z.string() });

// ------------------------------------------------------------------ forms
const password = z
  .string()
  .min(10, "At least 10 characters")
  .max(128)
  .refine(
    (v) => [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(v)).length >= 3,
    "Use at least three of: lower case, upper case, digits, symbols",
  );

export const LoginForm = z.object({
  email: z.string().trim().email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
export type LoginForm = z.infer<typeof LoginForm>;

export const RegisterForm = z.object({
  full_name: z.string().trim().max(120).optional().default(""),
  email: z.string().trim().email("Enter a valid email"),
  password,
  country: z.string().length(2).optional().or(z.literal("")),
  confirm_age_18: z.literal(true, { message: "You must be 18 or older" }),
  accept_terms: z.literal(true, { message: "Please accept the terms" }),
});
export type RegisterForm = z.input<typeof RegisterForm>;

export const ForgotForm = z.object({ email: z.string().trim().email("Enter a valid email") });
export const ResetForm = z
  .object({ password, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "Passwords do not match", path: ["confirm"] });

export const PasswordSetForm = z
  .object({ current_password: z.string().optional(), password, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "Passwords do not match", path: ["confirm"] });
export type PasswordSetForm = z.infer<typeof PasswordSetForm>;

export const SlipForm = z
  .object({
    target_odds: z.coerce.number().min(1.5, "Minimum 1.5").max(200, "Maximum 200"),
    min_legs: z.coerce.number().int().min(2).max(6),
    max_legs: z.coerce.number().int().min(2).max(6),
    days_ahead: z.coerce.number().int().min(0).max(14),
    prefer_value: z.boolean().default(false),
  })
  .refine((v) => v.max_legs >= v.min_legs, { message: "Max legs must be at least min legs", path: ["max_legs"] });
export type SlipFormInput = z.input<typeof SlipForm>;
export type SlipFormOutput = z.output<typeof SlipForm>;

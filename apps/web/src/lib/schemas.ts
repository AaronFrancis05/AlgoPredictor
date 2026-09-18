/**
 * Zod schemas: runtime validation of API responses (mirrors apps/api/app/schemas) and of every form.
 * Types are inferred from the schemas, so there is one source of truth on the client.
 */
import { z } from "zod";

export const PickSide = z.enum(["home", "draw", "away"]);

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
});
export type Pick = z.infer<typeof Pick>;

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
  plan: z.string(),
  entitlements: Entitlements,
  has_api_key: z.boolean(),
  has_password: z.boolean(),
  google_linked: z.boolean(),
});
export type User = z.infer<typeof User>;

export const AuthResult = z.object({ user: User, csrf_token: z.string(), access_token_expires_in: z.number() });
export const Message = z.object({ message: z.string() });
export const Redirect = z.object({ url: z.string().url() });
export const Subscription = z.object({
  plan_code: z.string(), provider: z.string(), status: z.string(), current_period_end: z.string().nullable(),
  cancel_at_period_end: z.boolean(),
});

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

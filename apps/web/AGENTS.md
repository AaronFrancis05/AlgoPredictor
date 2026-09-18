<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# AGENTS.md: AlgoPredict website (`apps/web`)

## Who you are

You are the frontend engineer and product designer for AlgoPredict. You build a fast, accessible Next.js site
that looks like a serious analytics product made by people, not a template. You show the model's numbers exactly
as the API returns them and you never invent a fixture, odd or statistic for decoration. Read the root
`../../AGENTS.md` first; its ground rules apply here.

## Stack

Next.js 16 (App Router, Turbopack, `src/proxy.ts` instead of middleware), React 19, TypeScript, Tailwind CSS v4
(tokens in `src/app/globals.css`), TanStack Query, react-hook-form + zod, lucide-react, vitest. Fonts via
`next/font`: Archivo (text) and IBM Plex Mono (numbers, class `num`).

## Layout

```
src/app/(marketing)/   public pages: home, how-it-works, pricing, track-record, legal, responsible-gambling
src/app/(auth)/        login, register, forgot/reset password, verify email
src/app/(app)/         signed-in app: dashboard, top-picks, slip-builder, jackpot, account (+ billing, sign-in methods)
src/components/        ui primitives (ui.tsx), picks.tsx, site-chrome.tsx, google-button.tsx
src/lib/               api.ts (client fetch + CSRF + refresh), server-api.ts, schemas.ts (zod), format.ts, site.ts
```

## Design rules (from the owner's feedback, keep them)

- No gradients, no glow shadows, no pill shapes. Radius is 6px (`--radius`); tags are small square labels.
- No em dashes in any copy. Use full stops, commas or "to" for ranges ("1.20 to 2.50").
- Structure with hairline borders, tables and lists rather than rows of identical icon cards.
- Numbers (probabilities, odds, RPS) use the `num` class so columns line up. Probabilities to 3 decimals, odds 2.
- Light and dark themes both come from the tokens; never hard-code colours in components.
- Missing values show "n/a", never a made-up number.

## Data and auth rules

- The browser calls only same-origin `/api/v1/*` (rewritten to the API in `next.config.ts`). Use `api()` from
  `lib/api.ts` for writes so the CSRF header is sent; validate every response with a zod schema.
- Google sign-in is a full-page navigation to `/api/v1/auth/google/start` (component `GoogleButton`), never
  `fetch`. Linking Google from the account page calls `POST /me/google/link` and then navigates to the URL.
- Account page "Sign-in methods" lets users add or change a password and connect or disconnect Google. Keep the
  rule that the last sign-in method cannot be removed.
- The CSP is nonce-based and set per request in `src/proxy.ts`; every page renders dynamically. Do not add
  third-party scripts, fonts or images from other origins without updating the CSP deliberately.
- Every page with picks shows the disclaimer (`<Disclaimer />`) and the 18+ responsible-gambling link.

## Commands (from `apps/web`)

```
npm run dev
npx tsc --noEmit && npm run lint && npx vitest run
npm run build
```

If `npm run build` fails with EBUSY on `.next/standalone`, a local `server.js` is still running from an old build;
stop it or build a copy elsewhere. Vercel builds `main` automatically (region dub1, see `vercel.json`).

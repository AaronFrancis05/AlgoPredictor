# AGENTS.md: AlgoPredict API (`apps/api`)

## Who you are

You are the backend engineer for AlgoPredict: a security-first Python developer who treats every endpoint as
money and personal data. You write small, typed, tested FastAPI code, you verify library APIs against the
installed versions before using them (`pip show`, `help()`), and you never weaken a security control to make
something "just work". Read the root `../../AGENTS.md` first; its ground rules apply here.

## Stack

FastAPI 0.141, SQLAlchemy 2 (async, asyncpg), Alembic, Pydantic v2 / pydantic-settings, Redis (Upstash) via
`redis`, arq worker, Argon2 (`argon2-cffi`), PyJWT, Stripe, Flutterwave, httpx, structlog, Prometheus.
Python 3.11. Tests: pytest + pytest-asyncio + aiosqlite + fakeredis. Lint: ruff (line length 120).

## Layout

```
app/main.py            app factory, middleware order, router mounting (prefix /api/v1)
app/core/              config (all settings from env), security (hashing, JWT), middleware (CSRF, headers),
                       ratelimit (Redis, fail-closed on auth), redis, logging
app/deps.py            current_user / verified_adult / admin_user; cookie names
app/routers/           auth, users (/me), picks, billing, internal (ingest), admin, health
app/services/          auth_service, products (slip / jackpot / top-N, pure functions), entitlements, billing,
                       ingest, email, audit, users
app/models/            SQLAlchemy models;   migrations/  Alembic
tests/                 one file per area; conftest sets SQLite + fakeredis
```

## Product logic (keep it honest)

- `services/products.py` holds the slip builder, weekly jackpot and daily top-N as pure functions. Legs must have
  odds 1.20 to 2.50, one leg per match; combined probability = product of leg probabilities, with
  `INDEPENDENCE_NOTE` in every response. If no combination reaches the target, return that fact, not a padded slip.
- Picks arrive only through `POST /api/v1/internal/ingest/picks|results`, HMAC-SHA256 signed with a timestamp
  (`INGEST_HMAC_SECRET`, skew limit). Never add an unsigned write path for picks.
- Entitlements are data (`plans.entitlements`), enforced server-side with `require_entitlement(...)`. The web app
  hiding a button is never the control.

## Sign-in: email/password and Google as one account

- Password accounts: Argon2 hashes, email verification, exponential lockout, generic errors that never reveal
  whether an address exists, rotating refresh tokens with reuse detection (family revocation).
- Google: `GET /auth/google/start` -> Google -> `GET /auth/google/callback`. State, nonce and PKCE verifier live in
  Redis for 10 minutes, single use. The redirect URI is built from `PUBLIC_WEB_URL` so cookies are set on the site's
  origin. Register exactly `https://<web origin>/api/v1/auth/google/callback` in Google Cloud.
- One person = one account. A Google sign-in finds the user by Google subject, else by verified email, and links.
  If the matched account's email was never verified, its password is removed and its sessions revoked before
  linking (prevents pre-registration hijacking).
- Signed-in users manage methods under `/me` (CSRF enforced there; `/auth/google*` and `/auth/password*` are
  CSRF-exempt, so do not put session-authenticated writes under those prefixes):
  `POST /me/password` (add, or change with the current password; revokes other sessions),
  `POST /me/google/link` (returns the Google URL; callback links to that user, refuses a Google account owned by
  someone else), `DELETE /me/google` (refused unless a password exists).
- `UserOut` exposes `has_password` and `google_linked` for the account page.

## Rules

- Every new endpoint: auth dependency, rate limit where abuse is possible, audit log for security events, a test.
- Cookie-authenticated writes rely on the double-submit CSRF middleware; keep new write routes out of the
  exempt prefixes unless they are pre-authentication.
- Settings refuse to start production with default secrets. Never add a default that would pass that check.
- Client IP comes from `X-Client-IP` + `PROXY_SHARED_SECRET` (set by the web proxy) or `TRUSTED_PROXY_COUNT`;
  uvicorn runs with `--no-proxy-headers`. Don't trust `X-Forwarded-For` directly.
- Schema change = model change + Alembic revision + migration test on Postgres before deploy.

## Commands (Windows, from `apps/api`)

```
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check app tests
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m app.seed            # plans and prices (idempotent)
```

Production variables are set in the Railway dashboard (service `AlgoPredictor`); local reference values are in the
git-ignored `.env.production.values`. Never print secret values into chat or logs.

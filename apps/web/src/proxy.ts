import { NextResponse, type NextRequest } from "next/server";

import { visitorHeaders } from "@/lib/client-ip";

/**
 * Runs before every page request (Next.js 16 "proxy", formerly middleware):
 * 1. a fresh CSP nonce per request (Next applies it to its own scripts/styles automatically);
 * 2. signed-in areas redirect to /login when there is no session cookie at all. The real check is the API
 *    call itself (401 -> refresh -> login), so this is only a fast path, never the security boundary;
 * 3. /api/v1 calls (rewritten to FastAPI) get the visitor's IP in X-Client-IP, signed with PROXY_SHARED_SECRET.
 */
const APP_PREFIXES = ["/dashboard", "/live", "/history", "/top-picks", "/slip-builder", "/jackpot", "/account",
                      "/onboarding", "/admin"];

/** Origin of the live-events stream when it is served straight from the API (see lib/live-events.ts). */
const eventsOrigin = (() => {
  try {
    const url = process.env.NEXT_PUBLIC_EVENTS_URL;
    return url && /^https?:\/\//.test(url) ? new URL(url).origin : null;
  } catch {
    return null;
  }
})();

/** API calls are rewritten to FastAPI; tell it who the visitor is so its rate limits key on them, not on us. */
function forwardToApi(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.delete("x-client-ip");
  headers.delete("x-proxy-secret");
  for (const [k, v] of Object.entries(visitorHeaders(request.headers.get("x-forwarded-for")))) headers.set(k, v);
  return NextResponse.next({ request: { headers } });
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api/v1/")) return forwardToApi(request);

  if (APP_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    const hasSession = request.cookies.has("ap_csrf") || request.cookies.has("ap_access");
    if (!hasSession) {
      const url = request.nextUrl.clone();
      url.pathname = "/login";
      url.search = `?next=${encodeURIComponent(pathname + search)}`;
      return NextResponse.redirect(url);
    }
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'${isDev ? " 'unsafe-inline'" : ""}`,
    // style="" attributes (e.g. probability bar widths) cannot execute script; <style> elements still need the nonce
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src 'self'${eventsOrigin ? ` ${eventsOrigin}` : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    // checkout pages of the payment providers are reached by redirect (not form posts), 'self' is enough
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(isDev ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    "/api/v1/:path*",
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|icon|robots.txt|sitemap.xml|manifest.webmanifest).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};

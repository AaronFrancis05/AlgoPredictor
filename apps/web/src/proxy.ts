import { NextResponse, type NextRequest } from "next/server";

/**
 * Runs before every page request (Next.js 16 "proxy", formerly middleware):
 * 1. a fresh CSP nonce per request (Next applies it to its own scripts/styles automatically);
 * 2. signed-in areas redirect to /login when there is no session cookie at all. The real check is the API
 *    call itself (401 -> refresh -> login), so this is only a fast path, never the security boundary;
 * 3. /api/v1 calls (rewritten to FastAPI) get the visitor's IP in X-Client-IP, signed with PROXY_SHARED_SECRET.
 */
const APP_PREFIXES = ["/dashboard", "/live", "/history", "/top-picks", "/slip-builder", "/jackpot", "/account",
                      "/onboarding", "/admin"];

/**
 * The visitor's IP as seen by the load balancer in front of this server. Each trusted hop appends the address it
 * received the request from, so the real client is `WEB_TRUSTED_PROXY_COUNT` entries from the right. Anything
 * further left was sent by the client and can be forged. Local `next start` has no load balancer: Next itself fills
 * X-Forwarded-For with the socket address when the header is missing (count 1 then reads that value).
 */
function clientIp(request: NextRequest): string | null {
  const hops = Number(process.env.WEB_TRUSTED_PROXY_COUNT ?? "1");
  const parts = (request.headers.get("x-forwarded-for") ?? "").split(",").map((p) => p.trim()).filter(Boolean);
  return hops > 0 && parts.length >= hops ? parts[parts.length - hops] : null;
}

/** API calls are rewritten to FastAPI; tell it who the visitor is so its rate limits key on them, not on us. */
function forwardToApi(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.delete("x-client-ip");
  headers.delete("x-proxy-secret");
  const secret = process.env.PROXY_SHARED_SECRET;
  const ip = clientIp(request);
  if (secret && ip) {
    headers.set("x-client-ip", ip);
    headers.set("x-proxy-secret", secret);
  }
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
    "connect-src 'self'",
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

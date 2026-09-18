/**
 * The visitor's IP as seen by the load balancer in front of this server. Each trusted hop appends the address it
 * received the request from, so the real client is `WEB_TRUSTED_PROXY_COUNT` entries from the right. Anything
 * further left was sent by the client and can be forged. Local `next start` has no load balancer: Next itself fills
 * X-Forwarded-For with the socket address when the header is missing (count 1 then reads that value).
 * Unset or invalid means 0: no header is trusted until a positive integer is configured explicitly.
 */
export function clientIpFrom(forwardedFor: string | null): string | null {
  const configured = Number(process.env.WEB_TRUSTED_PROXY_COUNT);
  const hops = Number.isSafeInteger(configured) && configured > 0 ? configured : 0;
  const parts = (forwardedFor ?? "").split(",").map((p) => p.trim()).filter(Boolean);
  return hops > 0 && parts.length >= hops ? parts[parts.length - hops] : null;
}

/** Headers that tell the API who the visitor is (so its rate limits key on them, not on this server). */
export function visitorHeaders(forwardedFor: string | null): Record<string, string> {
  const secret = process.env.PROXY_SHARED_SECRET;
  const ip = clientIpFrom(forwardedFor);
  return secret && ip ? { "x-client-ip": ip, "x-proxy-secret": secret } : {};
}

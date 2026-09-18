"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { TZ_COOKIE } from "@/lib/format";

/** Tell the server the viewer's time zone, so pages it renders pick the viewer's "today", not the UTC one. */
function useTimeZoneCookie() {
  useEffect(() => {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (tz) document.cookie = `${TZ_COOKIE}=${encodeURIComponent(tz)}; path=/; max-age=31536000; samesite=lax`;
    } catch {
      // no Intl time zone: the server falls back to UTC
    }
  }, []);
}

export function Providers({ children }: { children: ReactNode }) {
  useTimeZoneCookie();
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            refetchOnWindowFocus: false,
            // never retry auth/permission/validation errors; retry transient ones twice
            retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

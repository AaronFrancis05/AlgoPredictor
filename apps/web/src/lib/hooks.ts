"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { User } from "@/lib/schemas";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api("/me", User), staleTime: 30_000 });
}

/** The current time, re-read every `everyMs` so views can move matches between phases as the clock passes. */
export function useNow(everyMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(id);
  }, [everyMs]);
  return now;
}

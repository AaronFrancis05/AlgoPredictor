"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { User } from "@/lib/schemas";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api("/me", User), staleTime: 30_000 });
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useMemo } from "react";

import { api } from "@/lib/api";
import { Follows, type Pick } from "@/lib/schemas";

type Kind = "match" | "league";

type FollowsApi = {
  matches: Set<string>;
  leagues: Set<string>;
  /** Followed directly or through its league. */
  isFollowed: (p: Pick) => boolean;
  toggle: (kind: Kind, target: string) => void;
};

const Ctx = createContext<FollowsApi | null>(null);
const KEY = ["follows"];

/** Signed-in area only: follow buttons and "Following" filters render nothing outside it. */
export function FollowsProvider({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: () => api("/me/follows", Follows), enabled, staleTime: 5 * 60_000 });
  const m = useMutation({
    mutationFn: ({ kind, target, on }: { kind: Kind; target: string; on: boolean }) =>
      api(`/me/follows/${kind}/${encodeURIComponent(target)}`, Follows, { method: on ? "PUT" : "DELETE" }),
    // optimistic: the star fills at once; rolled back if the request fails
    onMutate: async ({ kind, target, on }) => {
      await qc.cancelQueries({ queryKey: KEY });
      const before = qc.getQueryData<Follows>(KEY);
      const field = kind === "match" ? "matches" : "leagues";
      const list = before?.[field] ?? [];
      qc.setQueryData<Follows>(KEY, {
        matches: before?.matches ?? [], leagues: before?.leagues ?? [],
        [field]: on ? [...new Set([...list, target])] : list.filter((t) => t !== target),
      });
      return { before };
    },
    onError: (_e, _v, ctx) => qc.setQueryData(KEY, ctx?.before),
    onSuccess: (data) => qc.setQueryData(KEY, data),
    // overlapping toggles can settle out of order: refetch so the cache ends on the server's list
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  });

  const data = q.data;
  const matches = useMemo(() => new Set(data?.matches ?? []), [data]);
  const leagues = useMemo(() => new Set(data?.leagues ?? []), [data]);
  const isFollowed = useCallback(
    (p: Pick) => matches.has(p.prediction_id) || leagues.has(p.league_code), [matches, leagues]);
  const { mutate } = m;
  const toggle = useCallback((kind: Kind, target: string) => {
    const on = !(kind === "match" ? matches : leagues).has(target);
    mutate({ kind, target, on });
  }, [matches, leagues, mutate]);

  const value = useMemo(() => (enabled ? { matches, leagues, isFollowed, toggle } : null),
                        [enabled, matches, leagues, isFollowed, toggle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** null outside the signed-in area. */
export function useFollows(): FollowsApi | null {
  return useContext(Ctx);
}

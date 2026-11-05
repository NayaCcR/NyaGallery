"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { NyaApi } from "@/lib/api";
import type { AdminSection } from "@/lib/admin-sections";
import type { PluginsResponse } from "@/lib/types";

export const PLUGINS_QUERY_KEY = ["plugins"] as const;

/**
 * Installed plugins and the admin sections they hide while disabled. Shared by the sidebar,
 * the admin page and the plugins panel through React Query, so one request serves all of them.
 * Fails open: if the request fails, nothing is hidden.
 */
export function usePlugins() {
  const { token, me } = useAuth();
  const enabled = Boolean(token && me && me.role !== "guest");
  const queryClient = useQueryClient();
  const query = useQuery<PluginsResponse>({
    queryKey: PLUGINS_QUERY_KEY,
    queryFn: () => NyaApi.plugins(),
    enabled,
    staleTime: 60_000,
  });
  // Ready once the list loaded (or failed / is not applicable): callers wait for this before
  // touching plugin-provided APIs so a disabled platform is never requested during first paint.
  const ready = !enabled || query.isSuccess || query.isError;
  const disabledList = query.data?.disabled_sections;
  const disabledSections = useMemo(() => new Set((disabledList ?? []) as AdminSection[]), [disabledList]);
  const isSectionAvailable = useCallback((section: AdminSection) => !disabledSections.has(section), [disabledSections]);
  const setData = useCallback((next: PluginsResponse) => queryClient.setQueryData(PLUGINS_QUERY_KEY, next), [queryClient]);
  return { ...query, ready, disabledSections, isSectionAvailable, setData };
}

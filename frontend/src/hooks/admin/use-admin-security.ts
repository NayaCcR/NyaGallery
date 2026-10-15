"use client";

import { useCallback, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { NyaApi } from "@/lib/api";
import type {
  AccessLogItem,
  Role,
  SecurityLimitOverride,
  SecuritySettings,
  UserSummary,
} from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

type UseAdminSecurityOptions = {
  run: AdminActionRunner;
  onUsersLoaded: (users: UserSummary[]) => void;
};

export function useAdminSecurity({ run, onUsersLoaded }: UseAdminSecurityOptions) {
  const { t } = useI18n();
  const [securityDraft, setSecurityDraft] = useState<SecuritySettings | null>(null);
  const [accessLogs, setAccessLogs] = useState<AccessLogItem[]>([]);
  const [accessLogFilter, setAccessLogFilter] = useState("");
  const [accessLogAsset, setAccessLogAsset] = useState("");
  const [accessLogUser, setAccessLogUser] = useState("");
  const [accessLogType, setAccessLogType] = useState("");
  const [accessLogAfter, setAccessLogAfter] = useState("");
  const [accessLogBefore, setAccessLogBefore] = useState("");
  const [roleLimitTarget, setRoleLimitTarget] = useState<Role>("viewer");
  const [userLimitTarget, setUserLimitTarget] = useState("");

  const loadSecurity = useCallback(async () => {
    const [settings, logs, userList] = await Promise.all([
      NyaApi.securitySettings(),
      NyaApi.accessLogs(80, 0, accessLogFilter, { assetKey: accessLogAsset, userId: accessLogUser, accessType: accessLogType, createdAfter: accessLogAfter, createdBefore: accessLogBefore }),
      NyaApi.users(),
    ]);
    setSecurityDraft(settings);
    setAccessLogs(logs.items);
    onUsersLoaded(userList.items);
    setUserLimitTarget((current) => current || userList.items[0]?.username || "");
  }, [accessLogAfter, accessLogAsset, accessLogBefore, accessLogFilter, accessLogType, accessLogUser, onUsersLoaded]);

  const saveSecurity = useCallback(async () => {
    if (!securityDraft) return;
    const { updated_at: _updatedAt, updated_by_username: _updatedBy, ...payload } = securityDraft;
    const saved = await run(
      "security-save",
      () => NyaApi.updateSecuritySettings(payload),
      () => t("admin.security.saved")
    );
    if (saved) setSecurityDraft(saved);
  }, [run, securityDraft, t]);

  const patchSecurity = useCallback((patch: Partial<SecuritySettings>) => {
    setSecurityDraft((current) => (current ? { ...current, ...patch } : current));
  }, []);

  const patchRoleLimit = useCallback((role: string, patch: SecurityLimitOverride) => {
    setSecurityDraft((current) =>
      current
        ? {
            ...current,
            role_limits: updateLimitOverrides(current.role_limits, role, patch),
          }
        : current
    );
  }, []);

  const patchUserLimit = useCallback((username: string, patch: SecurityLimitOverride) => {
    if (!username) return;
    setSecurityDraft((current) =>
      current
        ? {
            ...current,
            user_limits: updateLimitOverrides(current.user_limits, username, patch),
          }
        : current
    );
  }, []);

  return {
    securityDraft,
    accessLogs,
    accessLogFilter,
    setAccessLogFilter,
    accessLogAsset,
    setAccessLogAsset,
    accessLogUser,
    setAccessLogUser,
    accessLogType,
    setAccessLogType,
    accessLogAfter,
    setAccessLogAfter,
    accessLogBefore,
    setAccessLogBefore,
    roleLimitTarget,
    setRoleLimitTarget,
    userLimitTarget,
    setUserLimitTarget,
    loadSecurity,
    saveSecurity,
    patchSecurity,
    patchRoleLimit,
    patchUserLimit,
  };
}

function updateLimitOverrides(
  current: Record<string, SecurityLimitOverride>,
  key: string,
  patch: SecurityLimitOverride
) {
  const target = key.trim();
  if (!target) return current;
  const next = { ...current };
  const item: SecurityLimitOverride = { ...(next[target] ?? {}), ...patch };
  for (const field of ["max_user_concurrency", "user_requests_per_minute", "user_bytes_per_minute"] as const) {
    const value = item[field];
    if (value == null || value <= 0) delete item[field];
  }
  if (Object.keys(item).length === 0) delete next[target];
  else next[target] = item;
  return next;
}

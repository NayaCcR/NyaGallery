"use client";

import { useCallback, useState } from "react";
import { ApiError, NyaApi } from "@/lib/api";
import type { BackendConfig, DeveloperConfigResponse, DeveloperConsoleResponse } from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

type UseAdminDeveloperOptions = {
  run: AdminActionRunner;
  onError: (message: string) => void;
};

export function useAdminDeveloper({ run, onError }: UseAdminDeveloperOptions) {
  const [configResponse, setConfigResponse] = useState<DeveloperConfigResponse | null>(null);
  const [configDraft, setConfigDraft] = useState<BackendConfig | null>(null);
  const [consoleStatus, setConsoleStatus] = useState<DeveloperConsoleResponse | null>(null);
  const [consolePasswordDraft, setConsolePasswordDraft] = useState({ username: "", password: "" });

  const loadDeveloperConfig = useCallback(async () => {
    try {
      const response = await NyaApi.developerConfig();
      setConfigResponse(response);
      setConfigDraft(response.config);
      return response;
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
      return null;
    }
  }, [onError]);

  const saveDeveloperConfig = useCallback(async () => {
    if (!configDraft) return null;
    const response = await run(
      "developer-config-save",
      () => NyaApi.updateDeveloperConfig(configDraft),
      () => "配置已写入，重启后完整生效"
    );
    if (response) {
      setConfigResponse(response);
      setConfigDraft(response.config);
    }
    return response;
  }, [configDraft, run]);

  const loadDeveloperConsole = useCallback(async () => {
    try {
      const response = await NyaApi.developerConsole();
      setConsoleStatus(response);
      return response;
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
      return null;
    }
  }, [onError]);

  const resetConsolePassword = useCallback(async () => {
    const username = consolePasswordDraft.username.trim();
    const password = consolePasswordDraft.password;
    if (!username || !password) {
      onError("请输入用户名和新密码");
      return null;
    }
    const response = await run(
      "developer-reset-password",
      () => NyaApi.developerResetPassword(username, password),
      (user) => `已重置 ${user.username} 的密码`
    );
    if (response) setConsolePasswordDraft({ username: "", password: "" });
    return response;
  }, [consolePasswordDraft.password, consolePasswordDraft.username, onError, run]);

  return {
    configResponse,
    configDraft,
    setConfigDraft,
    loadDeveloperConfig,
    saveDeveloperConfig,
    consoleStatus,
    loadDeveloperConsole,
    consolePasswordDraft,
    setConsolePasswordDraft,
    resetConsolePassword,
  };
}

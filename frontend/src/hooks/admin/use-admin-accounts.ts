"use client";

import { useCallback, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { ApiError, NyaApi } from "@/lib/api";
import type { ApiTokenSummary, Role, UserSummary } from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

type UseAdminAccountsOptions = {
  run: AdminActionRunner;
  onError: (message: string) => void;
};

export function useAdminAccounts({ run, onError }: UseAdminAccountsOptions) {
  const { t } = useI18n();
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "viewer" as Role });
  const [passwordDraft, setPasswordDraft] = useState({ oldPassword: "", newPassword: "", confirmPassword: "" });
  const [userPasswordDrafts, setUserPasswordDrafts] = useState<Record<string, string>>({});
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [tokenTarget, setTokenTarget] = useState("");
  const [tokenLabel, setTokenLabel] = useState("");
  const [tokenScopes, setTokenScopes] = useState("view, api");
  const [issuedToken, setIssuedToken] = useState<string | null>(null);
  const [apiTokens, setApiTokens] = useState<ApiTokenSummary[]>([]);

  const replaceUsers = useCallback((items: UserSummary[]) => {
    setUsers(items);
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      const response = await NyaApi.users();
      setUsers(response.items);
      return response.items;
    } catch (err) {
      onError(err instanceof ApiError ? err.message : String(err));
      return [];
    }
  }, [onError]);

  const loadTokensFor = useCallback(
    async (username: string, showToast = true) => {
      const target = username.trim();
      if (!target) return null;
      if (showToast) {
        const result = await run(
          "token-list",
          () => NyaApi.userTokens(target),
          (response) => t("admin.accounts.tokensLoaded", { count: response.items.length })
        );
        if (result) setApiTokens(result.items);
        return result;
      }
      try {
        const result = await NyaApi.userTokens(target);
        setApiTokens(result.items);
        return result;
      } catch (err) {
        onError(err instanceof ApiError ? err.message : String(err));
        return null;
      }
    },
    [onError, run, t]
  );

  const loadUserTokens = useCallback(
    async (username: string) => {
      await loadTokensFor(username);
    },
    [loadTokensFor]
  );

  const revokeUserToken = useCallback(
    async (tokenId: number, username: string) => {
      const result = await run(
        `token-revoke-${tokenId}`,
        () => NyaApi.revokeToken(tokenId),
        () => t("admin.accounts.tokenRevoked")
      );
      if (result) await loadTokensFor(username);
    },
    [loadTokensFor, run, t]
  );

  const issueTokenForTarget = useCallback(
    async (username: string) => {
      const target = username.trim();
      if (!target) return;
      await run("token", () => NyaApi.issueToken(target, tokenLabel.trim(), tokenScopes.split(/[,\n，]/).map((item) => item.trim()).filter(Boolean)), (result) => {
        setIssuedToken(result.token);
        void loadTokensFor(target, false);
        return t("admin.accounts.tokenIssued");
      });
    },
    [loadTokensFor, run, t, tokenLabel, tokenScopes]
  );

  const createUser = useCallback(async () => {
    if (!newUser.username || !newUser.password) return;
    const created = await run(
      "create-user",
      () => NyaApi.createUser(newUser.username, newUser.password, newUser.role),
      (user) => t("admin.accounts.userCreated", { username: user.username })
    );
    if (!created) return;
    setUsers((current) => {
      const others = current.filter((user) => user.username !== created.username);
      return [...others, created].sort((left, right) =>
        left.username.localeCompare(right.username) || left.id - right.id
      );
    });
    setNewUser((draft) => ({ ...draft, username: "", password: "" }));
  }, [newUser.password, newUser.role, newUser.username, run, t]);

  const changePassword = useCallback(async () => {
    if (!passwordDraft.oldPassword || !passwordDraft.newPassword) return;
    if (passwordDraft.newPassword !== passwordDraft.confirmPassword) {
      onError(t("admin.accounts.passwordMismatch"));
      return;
    }
    const result = await run(
      "change-password",
      () => NyaApi.changePassword(passwordDraft.oldPassword, passwordDraft.newPassword),
      () => t("admin.accounts.passwordUpdated")
    );
    if (result) setPasswordDraft({ oldPassword: "", newPassword: "", confirmPassword: "" });
  }, [onError, passwordDraft.confirmPassword, passwordDraft.newPassword, passwordDraft.oldPassword, run, t]);

  const resetUserPassword = useCallback(
    async (username: string) => {
      const newPassword = userPasswordDrafts[username] ?? "";
      if (!newPassword) {
        onError(t("admin.accounts.enterNewPassword"));
        return;
      }
      const updated = await run(
        `user-password-${username}`,
        () => NyaApi.resetUserPassword(username, newPassword),
        (user) => t("admin.accounts.passwordResetFor", { username: user.username })
      );
      if (!updated) return;
      setUserPasswordDrafts((drafts) => ({ ...drafts, [username]: "" }));
      setUsers((current) => current.map((user) => (user.username === updated.username ? updated : user)));
    },
    [onError, run, t, userPasswordDrafts]
  );

  const updateTokenScopes = useCallback(
    async (tokenId: number, scopes: string[] | null) => {
      const result = await run(`token-scopes-${tokenId}`, () => NyaApi.updateTokenScopes(tokenId, scopes ?? undefined), () => t("admin.accounts.tokenScopesUpdated"));
      if (result) setApiTokens((tokens) => tokens.map((token) => token.id === result.id ? result : token));
    },
    [loadTokensFor, run, t, tokenTarget]
  );

  return {
    newUser,
    setNewUser,
    passwordDraft,
    setPasswordDraft,
    userPasswordDrafts,
    setUserPasswordDrafts,
    users,
    replaceUsers,
    loadUsers,
    tokenTarget,
    setTokenTarget,
    tokenLabel,
    setTokenLabel,
    tokenScopes,
    setTokenScopes,
    issuedToken,
    apiTokens,
    loadTokensFor,
    loadUserTokens,
    revokeUserToken,
    issueTokenForTarget,
    updateTokenScopes,
    createUser,
    changePassword,
    resetUserPassword,
  };
}

"use client";

import type { Dispatch, SetStateAction } from "react";
import { KeyRound, LockKeyhole, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyLine } from "@/components/admin/admin-fields";
import { TokenList } from "@/components/admin/admin-operation-rows";
import { useI18n } from "@/components/providers/locale-provider";
import { cn } from "@/lib/utils";
import type { ApiTokenSummary, Role, UserSummary } from "@/lib/types";

const ADMIN_CREATABLE_ROLES: Role[] = ["viewer", "editor", "admin"];
const DEVELOPER_CREATABLE_ROLES: Role[] = [...ADMIN_CREATABLE_ROLES, "developer"];

type NewUserDraft = {
  username: string;
  password: string;
  role: Role;
};

type PasswordDraft = {
  oldPassword: string;
  newPassword: string;
  confirmPassword: string;
};

type AdminAccountsPanelProps = {
  isAdmin: boolean;
  isDeveloper: boolean;
  currentUsername: string;
  busy: string | null;
  newUser: NewUserDraft;
  onNewUserChange: Dispatch<SetStateAction<NewUserDraft>>;
  onCreateUser: () => unknown;
  tokenTarget: string;
  onTokenTargetChange: (value: string) => void;
  tokenLabel: string;
  onTokenLabelChange: (value: string) => void;
  tokenScopes: string;
  onTokenScopesChange: (value: string) => void;
  issuedToken: string | null;
  apiTokens: ApiTokenSummary[];
  onLoadTokens: (username: string) => unknown;
  onIssueToken: (username: string) => unknown;
  onRevokeToken: (tokenId: number, username: string) => unknown;
  onUpdateTokenScopes: (tokenId: number, scopes: string[] | null) => unknown;
  passwordDraft: PasswordDraft;
  onPasswordDraftChange: Dispatch<SetStateAction<PasswordDraft>>;
  users: UserSummary[];
  userPasswordDrafts: Record<string, string>;
  onUserPasswordDraftsChange: Dispatch<SetStateAction<Record<string, string>>>;
  onChangePassword: () => unknown;
  onResetUserPassword: (username: string) => unknown;
};

export function AdminAccountsPanel({
  isAdmin,
  isDeveloper,
  currentUsername,
  busy,
  newUser,
  onNewUserChange,
  onCreateUser,
  tokenTarget,
  onTokenTargetChange,
  tokenLabel,
  onTokenLabelChange,
  tokenScopes,
  onTokenScopesChange,
  issuedToken,
  apiTokens,
  onLoadTokens,
  onIssueToken,
  onRevokeToken,
  onUpdateTokenScopes,
  passwordDraft,
  onPasswordDraftChange,
  users,
  userPasswordDrafts,
  onUserPasswordDraftsChange,
  onChangePassword,
  onResetUserPassword,
}: AdminAccountsPanelProps) {
  const { t } = useI18n();
  const activeTokenTarget = isAdmin ? tokenTarget : currentUsername;
  const creatableRoles = isDeveloper ? DEVELOPER_CREATABLE_ROLES : ADMIN_CREATABLE_ROLES;

  return (
    <>
      {isAdmin && (
        <section className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <UserPlus className="h-4 w-4" /> {t("admin.accounts.createUser")}
          </h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>{t("auth.username")}</Label>
              <Input value={newUser.username} onChange={(e) => onNewUserChange((user) => ({ ...user, username: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>{t("auth.password")}</Label>
              <Input type="password" value={newUser.password} onChange={(e) => onNewUserChange((user) => ({ ...user, password: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>{t("admin.accounts.role")}</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm focus-ring"
                value={newUser.role}
                onChange={(e) => onNewUserChange((user) => ({ ...user, role: e.target.value as Role }))}
              >
                {creatableRoles.map((role) => <option key={role} value={role}>{role}</option>)}
              </select>
            </div>
          </div>
          {!isDeveloper && (
            <p className="text-xs text-muted-foreground">
              {t("admin.accounts.developerCreateHint")}
            </p>
          )}
          <Button size="sm" disabled={!newUser.username || !newUser.password || busy === "create-user"} onClick={onCreateUser}>
            {t("admin.accounts.create")}
          </Button>
        </section>
      )}

      <section className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <KeyRound className="h-4 w-4" /> {t("admin.accounts.issueToken")}
        </h2>
        <div className="flex flex-wrap items-end gap-2">
          {isAdmin ? (
            <div className="grow space-y-1.5">
              <Label>{t("auth.username")}</Label>
              <Input value={tokenTarget} onChange={(e) => onTokenTargetChange(e.target.value)} />
            </div>
          ) : (
            <div className="grow space-y-1.5">
              <Label>{t("admin.accounts.currentUser")}</Label>
              <Input value={currentUsername} readOnly />
            </div>
          )}
          <div className="grow space-y-1.5">
            <Label>{t("admin.accounts.tokenLabel")}</Label>
            <Input value={tokenLabel} onChange={(e) => onTokenLabelChange(e.target.value)} placeholder={t("admin.accounts.tokenLabelPlaceholder")} />
          </div>
          <div className="grow space-y-1.5">
            <Label htmlFor="token-scopes">{t("admin.accounts.tokenScopes")}</Label>
            <Input id="token-scopes" value={tokenScopes} onChange={(event) => onTokenScopesChange(event.target.value)} placeholder="view, api" />
          </div>
          <Button variant="outline" disabled={busy === "token-list" || !activeTokenTarget} onClick={() => onLoadTokens(activeTokenTarget)}>
            {t("admin.accounts.viewExisting")}
          </Button>
          <Button disabled={busy === "token" || !activeTokenTarget} onClick={() => onIssueToken(activeTokenTarget)}>
            {t("admin.accounts.issue")}
          </Button>
        </div>
        {issuedToken && (
          <div className="space-y-1 rounded-md border border-border bg-muted p-3 text-xs">
            <p className="text-muted-foreground">{t("admin.accounts.saveTokenNow")}</p>
            <code className="block break-all font-mono">{issuedToken}</code>
          </div>
        )}
        <div className="space-y-2">
          <h3 className="text-xs font-medium uppercase text-muted-foreground">
            {isAdmin && tokenTarget && tokenTarget !== currentUsername
              ? t("admin.accounts.userTokens", { username: tokenTarget })
              : t("admin.accounts.currentTokens")}
          </h3>
          <TokenList tokens={apiTokens} busy={busy} onRevoke={(tokenId) => onRevokeToken(tokenId, activeTokenTarget)} onUpdateScopes={onUpdateTokenScopes} />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-border bg-card p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <LockKeyhole className="h-4 w-4" /> {t("admin.accounts.resetPassword")}
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1.5">
            <Label>{t("admin.accounts.oldPassword")}</Label>
            <Input
              type="password"
              autoComplete="current-password"
              value={passwordDraft.oldPassword}
              onChange={(e) => onPasswordDraftChange((draft) => ({ ...draft, oldPassword: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("admin.accounts.newPassword")}</Label>
            <Input
              type="password"
              autoComplete="new-password"
              value={passwordDraft.newPassword}
              onChange={(e) => onPasswordDraftChange((draft) => ({ ...draft, newPassword: e.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t("admin.accounts.confirmPassword")}</Label>
            <Input
              type="password"
              autoComplete="new-password"
              value={passwordDraft.confirmPassword}
              onChange={(e) => onPasswordDraftChange((draft) => ({ ...draft, confirmPassword: e.target.value }))}
            />
          </div>
        </div>
        <Button
          size="sm"
          disabled={
            busy === "change-password" ||
            !passwordDraft.oldPassword ||
            !passwordDraft.newPassword ||
            passwordDraft.newPassword !== passwordDraft.confirmPassword
          }
          onClick={onChangePassword}
        >
          {t("admin.accounts.saveNewPassword")}
        </Button>
        {isAdmin && (
          <div className="space-y-2 border-t border-border pt-3">
            <div>
              <h3 className="text-xs font-medium uppercase text-muted-foreground">{t("admin.accounts.existingUsers")}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("admin.accounts.existingUsersHint")}
              </p>
            </div>
            {users.length === 0 ? (
              <EmptyLine text={t("admin.accounts.emptyUsers")} />
            ) : (
              <div className="overflow-hidden rounded-lg border border-border text-xs">
                {users.map((user) => {
                  const isAdminUser = user.role === "admin" || user.role === "developer";
                  const passwordValue = userPasswordDrafts[user.username] ?? "";
                  const busyKey = `user-password-${user.username}`;
                  return (
                    <div
                      key={user.id}
                      className="grid gap-2 border-b border-border p-3 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_90px_minmax(180px,260px)_auto] sm:items-center"
                    >
                      <div className="min-w-0">
                        <div className="truncate font-medium">{user.username}</div>
                        <div className="text-muted-foreground">ID {user.id}</div>
                      </div>
                      <span
                        className={cn(
                          "w-fit rounded-full px-2 py-0.5 font-medium",
                          isAdminUser
                            ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                            : "bg-muted text-muted-foreground"
                        )}
                      >
                        {user.role}
                      </span>
                      {isAdminUser ? (
                        <div className="text-muted-foreground sm:col-span-2">
                          {t("admin.accounts.privilegedPasswordHint")}
                        </div>
                      ) : (
                        <>
                          <Input
                            type="password"
                            autoComplete="new-password"
                            value={passwordValue}
                            onChange={(e) =>
                              onUserPasswordDraftsChange((drafts) => ({
                                ...drafts,
                                [user.username]: e.target.value,
                              }))
                            }
                            placeholder={t("admin.accounts.newPassword")}
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={!passwordValue || busy === busyKey}
                            onClick={() => onResetUserPassword(user.username)}
                          >
                            {t("admin.accounts.reset")}
                          </Button>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>
    </>
  );
}

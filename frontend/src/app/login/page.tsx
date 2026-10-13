"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { KeyRound, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/components/providers/auth-provider";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { useRegistrationStatus } from "@/lib/hooks";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();
  const { t } = useI18n();
  const toast = useToast();
  const registration = useRegistrationStatus();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);

  const registrationMode = registration.data?.mode ?? "closed";
  const registrationEnabled = registration.data?.enabled ?? false;
  const inviteRequired = registration.data?.invite_required ?? false;
  const passwordMinLength = registration.data?.password_min_length ?? 1;
  const usernameMinLength = registration.data?.username_min_length ?? 1;
  const usernameMaxLength = registration.data?.username_max_length ?? 64;
  const activeMode = registrationEnabled ? mode : "login";

  async function submit() {
    if (!username.trim() || !password) return;
    setBusy(true);
    try {
      if (activeMode === "register") {
        await register(username.trim(), password, inviteRequired ? inviteCode : undefined, remember);
        toast.success(t("auth.registerSuccess"));
      } else {
        await login(username.trim(), password, remember);
        toast.success(t("auth.loginSuccess"));
      }
      router.push("/");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const usernameInvalid =
    username.trim().length > 0 &&
    (username.trim().length < usernameMinLength || username.trim().length > usernameMaxLength);
  const passwordInvalid = password.length > 0 && password.length < passwordMinLength;
  const submitDisabled =
    busy ||
    !username.trim() ||
    !password ||
    (activeMode === "register" && (usernameInvalid || passwordInvalid || (inviteRequired && !inviteCode.trim())));

  return (
    <div className="container max-w-md py-16">
      <div className="rounded-lg border border-border bg-card p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary text-primary-foreground">
            <KeyRound className="h-5 w-5" />
          </span>
          <div>
            <h1 className="text-lg font-semibold">
              {activeMode === "register" ? t("auth.register") : t("auth.login")}
            </h1>
            <p className="text-xs text-muted-foreground">
              {activeMode === "register" ? t("auth.registerDescription") : t("auth.loginDescription")}
            </p>
          </div>
        </div>

        {registrationEnabled && (
          <div className="mb-5 grid grid-cols-2 gap-1 rounded-md border border-border bg-muted/40 p-1 text-sm">
            <button
              type="button"
              className={`rounded px-3 py-1.5 transition-colors ${activeMode === "login" ? "bg-background shadow-sm" : "text-muted-foreground"}`}
              onClick={() => setMode("login")}
            >
              {t("auth.login")}
            </button>
            <button
              type="button"
              className={`rounded px-3 py-1.5 transition-colors ${activeMode === "register" ? "bg-background shadow-sm" : "text-muted-foreground"}`}
              onClick={() => setMode("register")}
            >
              {t("auth.register")}
            </button>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor="username">{t("auth.username")}</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
            {activeMode === "register" && (
              <p className="text-xs text-muted-foreground">
                {t("auth.usernameHint", { min: usernameMinLength, max: usernameMaxLength })}
              </p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">{t("auth.password")}</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={activeMode === "register" ? "new-password" : "current-password"}
            />
            {activeMode === "register" && (
              <p className="text-xs text-muted-foreground">{t("auth.passwordHint", { min: passwordMinLength })}</p>
            )}
          </div>
          {activeMode === "register" && inviteRequired && (
            <div className="space-y-1.5">
              <Label htmlFor="invite-code">{t("auth.inviteCode")}</Label>
              <Input
                id="invite-code"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                autoComplete="off"
              />
              <p className="text-xs text-muted-foreground">{t("auth.inviteCodeHint")}</p>
            </div>
          )}
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="h-4 w-4 accent-primary"
            />
            {t("auth.remember30Days")}
          </label>
          <Button type="submit" className="w-full" disabled={submitDisabled}>
            {activeMode === "register" ? (
              <>
                <UserPlus className="h-4 w-4" /> {t("auth.register")}
              </>
            ) : (
              t("auth.login")
            )}
          </Button>
        </form>

        {registration.isSuccess && registrationMode === "closed" && (
          <p className="mt-4 text-center text-xs text-muted-foreground">{t("auth.registerClosedHint")}</p>
        )}
        {registration.isSuccess && registrationMode === "invite" && activeMode === "login" && (
          <p className="mt-4 text-center text-xs text-muted-foreground">{t("auth.registerInviteOnlyHint")}</p>
        )}
      </div>
    </div>
  );
}

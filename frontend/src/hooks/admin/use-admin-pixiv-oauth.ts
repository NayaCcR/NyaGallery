"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { ApiError, NyaApi } from "@/lib/api";
import type { AdminActionRunner } from "./use-admin-action";

const PIXIV_OAUTH_SESSION_KEY = "nya.pixiv.oauth";

type PixivVisibleSession = {
  id: string;
  status: string;
  message?: string | null;
  error?: string | null;
};

type UseAdminPixivOAuthOptions = {
  busy: string | null;
  run: AdminActionRunner;
  supportsBrowserOAuthLogin?: boolean;
  setPixivRefreshToken: (value: string) => void;
  setLastPixivUser: (value: Record<string, unknown> | null) => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

export type PixivOAuthInputKind =
  | "empty"
  | "code"
  | "login"
  | "post_redirect"
  | "start"
  | "callback"
  | "third_party"
  | "unknown";

export function useAdminPixivOAuth({
  busy,
  run,
  supportsBrowserOAuthLogin,
  setPixivRefreshToken,
  setLastPixivUser,
  onError,
  onSuccess,
}: UseAdminPixivOAuthOptions) {
  const { t } = useI18n();
  const [pixivVisibleSession, setPixivVisibleSession] = useState<PixivVisibleSession | null>(null);
  const [pixivOAuthCallback, setPixivOAuthCallback] = useState("");
  const [pixivOAuthVerifier, setPixivOAuthVerifier] = useState("");
  const [pixivOAuthUrl, setPixivOAuthUrl] = useState("");

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(PIXIV_OAUTH_SESSION_KEY);
      if (!raw) return;
      const session = JSON.parse(raw) as { code_verifier?: string; authorization_url?: string };
      setPixivOAuthVerifier(session.code_verifier || "");
      setPixivOAuthUrl(session.authorization_url || "");
    } catch {
      window.sessionStorage.removeItem(PIXIV_OAUTH_SESSION_KEY);
    }
  }, []);

  useEffect(() => {
    if (!pixivVisibleSession?.id || pixivVisibleSession.status !== "running") return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const session = await NyaApi.pixivOAuthVisibleStatus(pixivVisibleSession.id);
        if (cancelled) return;
        setPixivVisibleSession({
          id: session.id,
          status: session.status,
          message: session.message,
          error: session.error,
        });
        if (session.status === "success" && session.refresh_token) {
          setPixivRefreshToken(session.refresh_token);
          setLastPixivUser(session.user);
          onSuccess(t("admin.pixiv.visibleLoginTokenReceived"));
        }
        if (session.status === "error" && session.error) {
          onError(session.error);
        }
      } catch (err) {
        if (!cancelled) {
          onError(err instanceof ApiError ? err.message : String(err));
        }
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [onError, onSuccess, pixivVisibleSession?.id, pixivVisibleSession?.status, setLastPixivUser, setPixivRefreshToken, t]);

  const pixivOAuthContinueUrl = useMemo(() => pixivPostRedirectUrl(pixivOAuthCallback), [pixivOAuthCallback]);
  const pixivOAuthStartUrl = useMemo(() => pixivPostRedirectStartUrl(pixivOAuthCallback), [pixivOAuthCallback]);
  const pixivOAuthInputKind = useMemo(() => pixivOAuthKind(pixivOAuthCallback), [pixivOAuthCallback]);
  const pixivOAuthOpenInputUrl = useMemo(
    () => (pixivOAuthInputKind === "login" || pixivOAuthInputKind === "start" ? pixivOAuthCallback.trim() : pixivOAuthContinueUrl),
    [pixivOAuthCallback, pixivOAuthContinueUrl, pixivOAuthInputKind]
  );
  const pixivOAuthHintText = useMemo(() => t(`admin.pixiv.oauthHints.${pixivOAuthInputKind}`), [pixivOAuthInputKind, t]);

  const pixivVisibleLoginDisabledReason = useMemo(() => {
    if (pixivVisibleSession?.status === "running") return t("admin.pixiv.visibleLoginRunning");
    if (busy === "pixiv-oauth-visible-start") return t("admin.pixiv.visibleLoginStarting");
    if (supportsBrowserOAuthLogin === false) return t("admin.pixiv.oauthMissingDependency");
    return "";
  }, [busy, pixivVisibleSession?.status, supportsBrowserOAuthLogin, t]);

  const startPixivOAuth = useCallback(async () => {
    const popup = window.open("about:blank", "_blank");
    if (popup) {
      try {
        popup.document.title = "Pixiv OAuth";
        popup.document.body.innerHTML = '<p style="font:14px system-ui,sans-serif;padding:24px;">Opening Pixiv login...</p>';
      } catch {
        /* best effort placeholder */
      }
    }
    const result = await run(
      "pixiv-oauth-start",
      () => NyaApi.pixivOAuthStart(),
      () => t("admin.pixiv.loginEntryGenerated")
    );
    if (!result) {
      popup?.close();
      return;
    }
    setPixivOAuthVerifier(result.code_verifier);
    setPixivOAuthUrl(result.authorization_url);
    setPixivOAuthCallback("");
    try {
      window.sessionStorage.setItem(
        PIXIV_OAUTH_SESSION_KEY,
        JSON.stringify({
          code_verifier: result.code_verifier,
          authorization_url: result.authorization_url,
        })
      );
    } catch {
      /* session storage is only a convenience */
    }
    if (popup) {
      try {
        popup.opener = null;
        popup.location.replace(result.authorization_url);
      } catch {
        window.open(result.authorization_url, "_blank", "noopener,noreferrer");
      }
    } else {
      onError(t("admin.pixiv.oauthErrors.popupBlocked"));
      window.open(result.authorization_url, "_blank", "noopener,noreferrer");
    }
  }, [onError, run, t]);

  const exchangePixivOAuth = useCallback(async () => {
    if (!pixivOAuthVerifier.trim()) {
      onError(t("admin.pixiv.oauthErrors.openLoginFirst"));
      return;
    }
    const callback = pixivOAuthCallback.trim();
    if (!callback) {
      onError(t("admin.pixiv.oauthErrors.pasteCallback"));
      return;
    }
    const continueUrl = pixivPostRedirectUrl(callback);
    if (continueUrl) {
      onError(t("admin.pixiv.oauthErrors.postRedirect"));
      window.open(continueUrl, "_blank", "noopener,noreferrer");
      return;
    }
    if (pixivOAuthKind(callback) === "login") {
      onError(t("admin.pixiv.oauthErrors.loginUrl"));
      window.open(callback, "_blank", "noopener,noreferrer");
      return;
    }
    if (pixivOAuthKind(callback) === "start") {
      onError(t("admin.pixiv.oauthErrors.startUrl"));
      return;
    }
    if (isPixivPicturesCallback(callback)) {
      onError(t("admin.pixiv.oauthErrors.thirdParty"));
      return;
    }
    const result = await run(
      "pixiv-oauth-exchange",
      () => NyaApi.pixivOAuthExchange({
        callback_url: callback,
        code_verifier: pixivOAuthVerifier.trim(),
      }),
      () => t("admin.pixiv.refreshTokenReceived")
    );
    if (!result) return;
    setPixivRefreshToken(result.refresh_token);
    setLastPixivUser(result.user);
    setPixivOAuthCallback("");
    try {
      window.sessionStorage.removeItem(PIXIV_OAUTH_SESSION_KEY);
    } catch {
      /* ignore */
    }
  }, [onError, pixivOAuthCallback, pixivOAuthVerifier, run, setLastPixivUser, setPixivRefreshToken, t]);

  const startVisiblePixivLogin = useCallback(async () => {
    const result = await run(
      "pixiv-oauth-visible-start",
      () => NyaApi.pixivOAuthVisibleStart({ timeout_seconds: 900 }),
      () => t("admin.pixiv.visibleLoginStarted")
    );
    if (!result) return;
    setPixivVisibleSession({
      id: result.id,
      status: result.status,
      message: result.message,
      error: result.error,
    });
  }, [run, t]);

  return {
    pixivVisibleSession,
    pixivOAuthCallback,
    setPixivOAuthCallback,
    pixivOAuthVerifier,
    pixivOAuthUrl,
    pixivOAuthInputKind,
    pixivOAuthOpenInputUrl,
    pixivOAuthStartUrl,
    pixivOAuthHintText,
    pixivVisibleLoginDisabledReason,
    startPixivOAuth,
    exchangePixivOAuth,
    startVisiblePixivLogin,
  };
}

function isPixivPicturesCallback(value: string): boolean {
  try {
    return new URL(value).hostname.toLowerCase().endsWith("pixiv.pictures");
  } catch {
    return false;
  }
}

function pixivOAuthKind(value: string): PixivOAuthInputKind {
  const text = value.trim();
  if (!text) return "empty";
  try {
    const url = new URL(text);
    const host = url.hostname.toLowerCase();
    if (host.endsWith("pixiv.pictures")) return "third_party";
    if (host === "app-api.pixiv.net" && url.pathname === "/web/v1/login") return "login";
    if (host === "accounts.pixiv.net" && url.pathname === "/post-redirect") return "post_redirect";
    if (host === "app-api.pixiv.net" && url.pathname === "/web/v1/users/auth/pixiv/start") return "start";
    if (host === "app-api.pixiv.net" && url.pathname === "/web/v1/users/auth/pixiv/callback" && url.searchParams.get("code")) {
      return "callback";
    }
    return "unknown";
  } catch {
    return /^[A-Za-z0-9_-]{20,}$/.test(text) ? "code" : "unknown";
  }
}

function pixivPostRedirectUrl(value: string): string | null {
  const clean = pixivPostRedirectStartUrl(value);
  if (!clean) return null;
  const rewritten = new URL("https://accounts.pixiv.net/post-redirect");
  rewritten.searchParams.set("return_to", clean);
  return rewritten.toString();
}

function pixivPostRedirectStartUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (url.hostname.toLowerCase() !== "accounts.pixiv.net" || url.pathname !== "/post-redirect") return null;
    const target = url.searchParams.get("return_to");
    if (!target) return null;
    const targetUrl = new URL(target);
    if (targetUrl.hostname.toLowerCase() !== "app-api.pixiv.net" || targetUrl.pathname !== "/web/v1/users/auth/pixiv/start") {
      return null;
    }
    const clean = new URL("https://app-api.pixiv.net/web/v1/users/auth/pixiv/start");
    for (const key of ["code_challenge", "code_challenge_method", "client", "via"]) {
      const raw = targetUrl.searchParams.get(key);
      if (raw) clean.searchParams.set(key, trimBeforeEmbeddedUrl(raw));
    }
    return clean.toString();
  } catch {
    return null;
  }
}

function trimBeforeEmbeddedUrl(value: string): string {
  const index = value.search(/https?:\/\//i);
  return index >= 0 ? value.slice(0, index) : value;
}

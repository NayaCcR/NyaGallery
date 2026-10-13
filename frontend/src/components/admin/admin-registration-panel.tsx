"use client";

import { Copy, RefreshCw, Ticket, Trash2 } from "lucide-react";
import { useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NumberField } from "@/components/admin/admin-fields";
import { formatDate } from "@/components/admin/admin-format";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { useAdminAction } from "@/hooks/admin/use-admin-action";
import { useAdminRegistration } from "@/hooks/admin/use-admin-registration";

export function AdminRegistrationPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const { busy, run } = useAdminAction({ onError: toast.error, onSuccess: toast.success });
  const {
    invites,
    label,
    setLabel,
    maxUses,
    setMaxUses,
    expiresInDays,
    setExpiresInDays,
    customCode,
    setCustomCode,
    createdCode,
    setCreatedCode,
    loadInvites,
    createInvite,
    revokeInvite,
  } = useAdminRegistration({ run });

  useEffect(() => {
    void loadInvites().catch(() => undefined);
  }, [loadInvites]);

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Ticket className="h-4 w-4" /> {t("admin.registration.title")}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("admin.registration.description")}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={busy === "registration-invite-refresh"}
          onClick={() => run("registration-invite-refresh", loadInvites, () => t("admin.registration.refreshed"))}
        >
          <RefreshCw className="h-4 w-4" /> {t("common.refresh")}
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-1.5">
          <span className="text-xs text-muted-foreground">{t("admin.registration.label")}</span>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={t("admin.registration.labelPlaceholder")} />
        </label>
        <NumberField label={t("admin.registration.maxUses")} value={maxUses} onChange={(value) => setMaxUses(Math.max(1, value))} />
        <NumberField label={t("admin.registration.expiresInDays")} value={expiresInDays} onChange={setExpiresInDays} suffix={t("admin.registration.days")} />
        <label className="space-y-1.5">
          <span className="text-xs text-muted-foreground">{t("admin.registration.customCode")}</span>
          <Input value={customCode} onChange={(e) => setCustomCode(e.target.value)} placeholder={t("admin.registration.customCodePlaceholder")} />
        </label>
      </div>

      <Button size="sm" disabled={busy === "registration-invite-create"} onClick={() => void createInvite()}>
        <Ticket className="h-4 w-4" /> {t("admin.registration.create")}
      </Button>

      {createdCode && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-border bg-muted/40 px-3 py-2">
          <div className="min-w-0">
            <div className="text-xs text-muted-foreground">{t("admin.registration.createdHint")}</div>
            <code className="break-all font-mono text-sm">{createdCode}</code>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void navigator.clipboard.writeText(createdCode);
                toast.success(t("common.copied"));
              }}
            >
              <Copy className="h-4 w-4" /> {t("common.copyLink")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setCreatedCode(null)}>
              {t("common.close")}
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-border">
        <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr_auto] gap-2 border-b border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <span>{t("admin.registration.columnCode")}</span>
          <span>{t("admin.registration.columnLabel")}</span>
          <span>{t("admin.registration.columnUses")}</span>
          <span>{t("admin.registration.columnExpires")}</span>
          <span />
        </div>
        {invites.map((invite) => (
          <div
            key={invite.id}
            className="grid grid-cols-[1.4fr_1fr_1fr_1fr_auto] items-center gap-2 border-b border-border px-3 py-2 text-sm last:border-b-0"
          >
            <span className="truncate font-mono text-xs">{invite.code_prefix}…</span>
            <span className="truncate">{invite.label || "-"}</span>
            <span>
              {invite.used_count} / {invite.max_uses}
            </span>
            <span className="text-xs text-muted-foreground">{invite.expires_at ? formatDate(invite.expires_at) : t("admin.registration.neverExpires")}</span>
            <div className="flex items-center justify-end gap-2">
              {invite.revoked_at ? (
                <Badge variant="secondary">{t("admin.registration.statusRevoked")}</Badge>
              ) : invite.expired ? (
                <Badge variant="secondary">{t("admin.registration.statusExpired")}</Badge>
              ) : invite.remaining_uses <= 0 ? (
                <Badge variant="secondary">{t("admin.registration.statusUsed")}</Badge>
              ) : (
                <Badge>{t("admin.registration.statusActive")}</Badge>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={busy === "registration-invite-revoke" || Boolean(invite.revoked_at)}
                onClick={() => void revokeInvite(invite.id)}
              >
                <Trash2 className="h-4 w-4" /> {t("admin.registration.revoke")}
              </Button>
            </div>
          </div>
        ))}
        {invites.length === 0 && (
          <div className="p-8 text-center text-sm text-muted-foreground">{t("admin.registration.empty")}</div>
        )}
      </div>
    </section>
  );
}

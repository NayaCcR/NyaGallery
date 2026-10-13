"use client";

import { useCallback, useState } from "react";
import { useI18n } from "@/components/providers/locale-provider";
import { NyaApi } from "@/lib/api";
import type { RegistrationInvite } from "@/lib/types";
import type { AdminActionRunner } from "./use-admin-action";

export function useAdminRegistration({ run }: { run: AdminActionRunner }) {
  const { t } = useI18n();
  const [invites, setInvites] = useState<RegistrationInvite[]>([]);
  const [label, setLabel] = useState("");
  const [maxUses, setMaxUses] = useState(1);
  const [expiresInDays, setExpiresInDays] = useState(0);
  const [customCode, setCustomCode] = useState("");
  const [createdCode, setCreatedCode] = useState<string | null>(null);

  const loadInvites = useCallback(async () => {
    const response = await NyaApi.registrationInvites();
    setInvites(response.items);
    return response.items;
  }, []);

  const createInvite = useCallback(async () => {
    const created = await run(
      "registration-invite-create",
      () =>
        NyaApi.createRegistrationInvite({
          label: label.trim(),
          code: customCode.trim() || null,
          max_uses: Math.max(1, Math.round(maxUses)),
          expires_in_days: expiresInDays > 0 ? Math.round(expiresInDays) : null,
        }),
      () => t("admin.registration.created")
    );
    if (!created) return null;
    setCreatedCode(created.code);
    setLabel("");
    setCustomCode("");
    setMaxUses(1);
    setExpiresInDays(0);
    await loadInvites();
    return created;
  }, [customCode, expiresInDays, label, loadInvites, maxUses, run, t]);

  const revokeInvite = useCallback(
    async (inviteId: number) => {
      const revoked = await run(
        "registration-invite-revoke",
        () => NyaApi.revokeRegistrationInvite(inviteId),
        () => t("admin.registration.revoked")
      );
      if (!revoked) return null;
      await loadInvites();
      return revoked;
    },
    [loadInvites, run, t]
  );

  return {
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
  };
}

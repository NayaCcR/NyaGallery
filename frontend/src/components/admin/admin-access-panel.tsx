"use client";

import { useEffect, useState } from "react";
import { FolderTree, Shield, Trash2, UsersRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { NyaApi } from "@/lib/api";
import type { PermissionGroup, ShareGroup, VirtualFolderSummary } from "@/lib/types";

export function AdminAccessPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const [groups, setGroups] = useState<ShareGroup[]>([]);
  const [permissions, setPermissions] = useState<PermissionGroup[]>([]);
  const [folders, setFolders] = useState<VirtualFolderSummary[]>([]);
  const [name, setName] = useState("");
  const [members, setMembers] = useState("");
  const [folderName, setFolderName] = useState("");
  const [folderQuery, setFolderQuery] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [access, roleGroups, virtualFolders] = await Promise.all([
      NyaApi.accessGroups(), NyaApi.permissionGroups(), NyaApi.virtualFolders(),
    ]);
    setGroups(access.items);
    setPermissions(roleGroups.items);
    setFolders(virtualFolders.items);
  }

  // The locale/toast helpers are stable for the lifetime of the admin page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void refresh().catch((error) => toast.error(error instanceof Error ? error.message : t("admin.access.loadFailed"))); }, []);

  async function createGroup() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await NyaApi.createAccessGroup(name.trim(), members.split(",").map((item) => item.trim()).filter(Boolean));
      setName(""); setMembers(""); await refresh(); toast.success(t("admin.access.saved"));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  async function deleteGroup(id: number) {
    setBusy(true);
    try { await NyaApi.deleteAccessGroup(id); await refresh(); toast.success(t("admin.access.deleted")); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  async function createFolder() {
    if (!folderName.trim() || !folderQuery.trim()) return;
    setBusy(true);
    try { await NyaApi.putVirtualFolder(folderName.trim(), folderQuery.trim()); setFolderName(""); setFolderQuery(""); await refresh(); toast.success(t("admin.access.saved")); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  return <div className="space-y-6">
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div><h2 className="flex items-center gap-2 text-sm font-medium"><UsersRound className="h-4 w-4" />{t("admin.access.shareGroups")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.access.shareGroupsHint")}</p></div>
      <div className="grid gap-3 md:grid-cols-[1fr_2fr_auto] md:items-end">
        <div className="space-y-1.5"><Label>{t("admin.access.groupName")}</Label><Input value={name} onChange={(event) => setName(event.target.value)} /></div>
        <div className="space-y-1.5"><Label>{t("admin.access.members")}</Label><Input value={members} onChange={(event) => setMembers(event.target.value)} placeholder={t("admin.access.membersPlaceholder")} /></div>
        <Button disabled={busy || !name.trim()} onClick={createGroup}>{t("admin.access.createGroup")}</Button>
      </div>
      <div className="divide-y divide-border rounded-md border border-border">
        {groups.length === 0 ? <p className="p-3 text-xs text-muted-foreground">{t("admin.access.emptyGroups")}</p> : groups.map((group) => <div key={group.id} className="flex items-center justify-between gap-3 p-3 text-xs"><div><div className="font-medium">{group.name}</div><div className="text-muted-foreground">{group.members.map((member) => member.username).join(", ") || t("admin.access.noMembers")}</div></div><Button variant="ghost" size="icon" title={t("admin.access.deleteGroup")} disabled={busy} onClick={() => deleteGroup(group.id)}><Trash2 className="h-4 w-4" /></Button></div>)}
      </div>
    </section>

    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div><h2 className="flex items-center gap-2 text-sm font-medium"><Shield className="h-4 w-4" />{t("admin.access.permissionGroups")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.access.permissionGroupsHint")}</p></div>
      <div className="grid gap-3 md:grid-cols-2">{permissions.map((item) => <div key={item.role} className="rounded-md border border-border p-3 text-xs"><div className="font-medium">{item.role}</div><div className="mt-1 text-muted-foreground">{item.permissions.join(" · ")}</div></div>)}</div>
    </section>

    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div><h2 className="flex items-center gap-2 text-sm font-medium"><FolderTree className="h-4 w-4" />{t("admin.access.virtualFolders")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.access.virtualFoldersHint")}</p></div>
      <div className="grid gap-3 md:grid-cols-[1fr_2fr_auto] md:items-end"><div className="space-y-1.5"><Label>{t("admin.access.folderName")}</Label><Input value={folderName} onChange={(event) => setFolderName(event.target.value)} /></div><div className="space-y-1.5"><Label>{t("admin.access.folderQuery")}</Label><Input value={folderQuery} onChange={(event) => setFolderQuery(event.target.value)} placeholder="tag:type/static" /></div><Button disabled={busy || !folderName.trim() || !folderQuery.trim()} onClick={createFolder}>{t("admin.access.createFolder")}</Button></div>
      <div className="space-y-2">{folders.map((folder) => <div key={folder.name} className="rounded-md border border-border p-3 text-xs"><div className="font-medium">{folder.name}</div><code className="text-muted-foreground">{folder.query}</code></div>)}</div>
    </section>
  </div>;
}

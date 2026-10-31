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
  const [assetKeys, setAssetKeys] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("");
  const [aclPermission, setAclPermission] = useState<"view" | "edit" | "upload">("view");
  const [shortAssetKeys, setShortAssetKeys] = useState("");
  const [shortExpiry, setShortExpiry] = useState("");
  const [shortResults, setShortResults] = useState<Array<{ asset_key: string; slug: string; url: string }>>([]);
  const [folderName, setFolderName] = useState("");
  const [folderQuery, setFolderQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [shareLogs, setShareLogs] = useState<Array<{ id: number; asset_key: string; status: string; client_ip: string; user_agent: string; created_at: string | null }>>([]);
  const [shareLogAsset, setShareLogAsset] = useState("");
  const [shareLogStatus, setShareLogStatus] = useState("");
  const [shareLogOffset, setShareLogOffset] = useState(0);

  async function refresh() {
    const [access, roleGroups, virtualFolders, logs] = await Promise.all([
      NyaApi.accessGroups(), NyaApi.permissionGroups(), NyaApi.virtualFolders(), NyaApi.shareAccessLogs(50, shareLogOffset, shareLogAsset, shareLogStatus),
    ]);
    setGroups(access.items);
    setShareLogs(logs.items);
    setPermissions(roleGroups.items);
    setFolders(virtualFolders.items);
  }

  // The locale/toast helpers are stable for the lifetime of the admin page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void refresh().catch((error) => toast.error(error instanceof Error ? error.message : t("admin.access.loadFailed"))); }, [shareLogOffset]);

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

  async function bindAssetsToGroup() {
    const keys = [...new Set(assetKeys.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean))];
    const groupId = Number(selectedGroup);
    if (!keys.length || !Number.isInteger(groupId)) return;
    setBusy(true);
    try {
      const result = await NyaApi.bulkBindAssetGroup(keys, groupId, aclPermission);
      setAssetKeys("");
      toast.success(t("admin.access.assetsBound", { count: result.bound }));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  async function createBulkShortLinks() {
    const keys = [...new Set(shortAssetKeys.split(/[\\s,]+/).map((item) => item.trim()).filter(Boolean))];
    if (!keys.length) return;
    setBusy(true);
    try {
      const response = await NyaApi.bulkCreateShortLinks(keys, shortExpiry ? new Date(shortExpiry).toISOString() : undefined);
      setShortResults(response.items);
      setShortAssetKeys("");
      toast.success(t("admin.access.shortLinksCreated", { count: response.items.length }));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
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
      <div className="space-y-3 border-t border-border pt-4">
        <h3 className="text-sm font-medium">{t("admin.access.bulkShare")}</h3>
        <textarea aria-label={t("admin.access.assetKeys")} value={assetKeys} onChange={(event) => setAssetKeys(event.target.value)} placeholder={t("admin.access.assetKeysHint")} className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
        <div className="grid gap-2 sm:grid-cols-[1fr_180px_auto]">
          <select aria-label={t("admin.access.selectGroup")} value={selectedGroup} onChange={(event) => setSelectedGroup(event.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="">{t("admin.access.selectGroup")}</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select>
          <select aria-label={t("admin.access.permission")} value={aclPermission} onChange={(event) => setAclPermission(event.target.value as "view" | "edit" | "upload")} className="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="view">{t("admin.access.viewOnly")}</option><option value="edit">{t("admin.access.edit")}</option><option value="upload">{t("admin.access.upload")}</option></select>
          <Button disabled={busy || !selectedGroup || !assetKeys.trim()} onClick={bindAssetsToGroup}>{t("admin.access.bindAssets")}</Button>
        </div>
      </div>
      <div className="space-y-3 border-t border-border pt-4">
        <h3 className="text-sm font-medium">{t("admin.access.bulkShortLinks")}</h3>
        <textarea aria-label={t("admin.access.assetKeys")} value={shortAssetKeys} onChange={(event) => setShortAssetKeys(event.target.value)} placeholder={t("admin.access.assetKeysHint")} className="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" />
        <div className="grid gap-2 sm:grid-cols-[1fr_auto]"><Input type="datetime-local" value={shortExpiry} onChange={(event) => setShortExpiry(event.target.value)} aria-label={t("admin.access.shortLinkExpiry")} /><Button disabled={busy || !shortAssetKeys.trim()} onClick={createBulkShortLinks}>{t("admin.access.createShortLinks")}</Button></div>
        {shortResults.length > 0 && <div className="divide-y divide-border rounded-md border border-border">{shortResults.map((item) => <div key={item.asset_key} className="flex flex-wrap items-center justify-between gap-2 p-2 text-xs"><code>{item.asset_key}</code><a className="break-all text-primary underline" href={item.url} target="_blank" rel="noreferrer">/{item.url.split("/s/").pop()}</a></div>)}</div>}
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

    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div><h2 className="flex items-center gap-2 text-sm font-medium">{t("admin.access.shareLogs")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.access.shareLogsHint")}</p></div>
      <div className="grid gap-2 sm:grid-cols-[1fr_160px_auto]"><Input value={shareLogAsset} onChange={(event) => { setShareLogAsset(event.target.value); setShareLogOffset(0); }} placeholder={t("admin.access.shareLogAsset")} /><select value={shareLogStatus} onChange={(event) => { setShareLogStatus(event.target.value); setShareLogOffset(0); }} className="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="">{t("admin.access.shareLogAllStatuses")}</option><option value="metadata">metadata</option><option value="preview">preview</option><option value="original">original</option></select><Button variant="outline" onClick={() => void refresh()} disabled={busy}>{t("common.refresh")}</Button></div>
      <div className="divide-y divide-border rounded-md border border-border">{shareLogs.length === 0 ? <p className="p-3 text-xs text-muted-foreground">{t("admin.access.emptyShareLogs")}</p> : shareLogs.map((log) => <div key={log.id} className="grid gap-1 p-3 text-xs sm:grid-cols-[1fr_100px_170px]"><code>{log.asset_key}</code><span className="text-muted-foreground">{log.status}</span><span className="text-muted-foreground">{log.created_at ?? "-"}</span><span className="truncate text-muted-foreground sm:col-span-3">{log.user_agent || log.client_ip || "-"}</span></div>)}</div>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground"><span>{t("admin.access.shareLogPage", { page: Math.floor(shareLogOffset / 50) + 1 })}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={busy || shareLogOffset === 0} onClick={() => setShareLogOffset((value) => Math.max(0, value - 50))}>{t("admin.access.shareLogPrevious")}</Button><Button variant="outline" size="sm" disabled={busy || shareLogs.length < 50} onClick={() => setShareLogOffset((value) => value + 50)}>{t("admin.access.shareLogNext")}</Button></div></div>
    </section>
  </div>;
}

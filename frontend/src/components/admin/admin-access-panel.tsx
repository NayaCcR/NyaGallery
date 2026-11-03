"use client";

import { useEffect, useState } from "react";
import { FolderTree, Shield, Trash2, UsersRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { NyaApi } from "@/lib/api";
import type { ShareAlbum, ShareAlbumPermission } from "@/lib/api";
import type { PermissionGroup, ShareGroup, VirtualFolderSummary } from "@/lib/types";

export function AdminAccessPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const [groups, setGroups] = useState<ShareGroup[]>([]);
  const [permissions, setPermissions] = useState<PermissionGroup[]>([]);
  const [folders, setFolders] = useState<VirtualFolderSummary[]>([]);
  const [albums, setAlbums] = useState<ShareAlbum[]>([]);
  const [albumName, setAlbumName] = useState("");
  const [albumDescription, setAlbumDescription] = useState("");
  const [albumAssetKeys, setAlbumAssetKeys] = useState("");
  const [selectedAlbum, setSelectedAlbum] = useState("");
  const [albumGroup, setAlbumGroup] = useState("");
  const [albumPermission, setAlbumPermission] = useState<ShareAlbumPermission>("view");
  const [name, setName] = useState("");
  const [inviteUsernames, setInviteUsernames] = useState<Record<number, string>>({});
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
    const [access, roleGroups, virtualFolders, logs, shareAlbums] = await Promise.all([
      NyaApi.accessGroups(), NyaApi.permissionGroups(), NyaApi.virtualFolders(), NyaApi.shareAccessLogs(50, shareLogOffset, shareLogAsset, shareLogStatus), NyaApi.shareAlbums(),
    ]);
    setGroups(access.items);
    setAlbums(shareAlbums.items);
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
      await NyaApi.createAccessGroup(name.trim(), []);
      setName(""); await refresh(); toast.success(t("admin.access.saved"));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  async function inviteGroupMember(groupId: number) {
    const username = (inviteUsernames[groupId] ?? "").trim();
    if (!username) return;
    setBusy(true);
    try {
      await NyaApi.inviteShareGroupMember(groupId, username);
      setInviteUsernames((current) => ({ ...current, [groupId]: "" }));
      toast.success(t("admin.access.inviteSent"));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  async function updateGroupMemberRole(groupId: number, userId: number, role: "admin" | "member") {
    setBusy(true);
    try { await NyaApi.setShareGroupMemberRole(groupId, userId, role); await refresh(); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
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

  function parseAlbumAssetKeys() {
    return [...new Set(albumAssetKeys.split(/[\\s,]+/).map((item) => item.trim()).filter(Boolean))];
  }

  async function saveAlbum() {
    if (!albumName.trim()) return;
    setBusy(true);
    try {
      const payload = { name: albumName.trim(), description: albumDescription.trim(), asset_keys: parseAlbumAssetKeys() };
      if (selectedAlbum) await NyaApi.updateShareAlbum(Number(selectedAlbum), payload);
      else await NyaApi.createShareAlbum(payload);
      setAlbumName(""); setAlbumDescription(""); setAlbumAssetKeys(""); setSelectedAlbum("");
      await refresh(); toast.success(t("admin.access.albumSaved"));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  function selectAlbum(value: string) {
    setSelectedAlbum(value);
    const album = albums.find((item) => String(item.id) === value);
    setAlbumName(album?.name ?? ""); setAlbumDescription(album?.description ?? ""); setAlbumAssetKeys(album?.asset_keys.join("\\n") ?? "");
  }

  async function deleteAlbum() {
    if (!selectedAlbum) return;
    setBusy(true);
    try { await NyaApi.deleteShareAlbum(Number(selectedAlbum)); setSelectedAlbum(""); setAlbumName(""); setAlbumDescription(""); setAlbumAssetKeys(""); await refresh(); toast.success(t("admin.access.deleted")); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  async function bindAlbumGroup() {
    if (!selectedAlbum || !albumGroup) return;
    setBusy(true);
    try { await NyaApi.bindShareAlbumGroup(Number(selectedAlbum), Number(albumGroup), albumPermission); setAlbumGroup(""); await refresh(); toast.success(t("admin.access.albumGroupBound")); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  async function unbindAlbumGroup(groupId: number) {
    if (!selectedAlbum) return;
    setBusy(true);
    try { await NyaApi.unbindShareAlbumGroup(Number(selectedAlbum), groupId); await refresh(); toast.success(t("admin.access.albumGroupUnbound")); }
    catch (error) { toast.error(error instanceof Error ? error.message : t("admin.access.saveFailed")); }
    finally { setBusy(false); }
  }

  return <div className="space-y-6">
    <section className="space-y-4 rounded-lg border border-border bg-card p-6 shadow-sm">
      <div><h2 className="flex items-center gap-2 text-sm font-medium"><UsersRound className="h-4 w-4" />{t("admin.access.shareGroups")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.access.shareGroupsHint")}</p></div>
      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
        <div className="space-y-1.5"><Label>{t("admin.access.groupName")}</Label><Input value={name} onChange={(event) => setName(event.target.value)} /></div>
        <Button disabled={busy || !name.trim()} onClick={createGroup}>{t("admin.access.createGroup")}</Button>
      </div>
      <div className="divide-y divide-border rounded-md border border-border">
        {groups.length === 0 ? <p className="p-3 text-xs text-muted-foreground">{t("admin.access.emptyGroups")}</p> : groups.map((group) => <div key={group.id} className="space-y-2 p-3 text-xs"><div className="flex items-center justify-between gap-3"><div className="font-medium">{group.name}</div><Button variant="ghost" size="icon" title={t("admin.access.deleteGroup")} disabled={busy} onClick={() => deleteGroup(group.id)}><Trash2 className="h-4 w-4" /></Button></div><div className="space-y-1">{group.members.map((member) => <div key={member.id} className="flex items-center justify-between gap-2"><span>{member.username}</span><select aria-label={t("admin.access.memberRole", { username: member.username })} value={member.role} disabled={busy} onChange={(event) => void updateGroupMemberRole(group.id, member.id, event.target.value as "admin" | "member")} className="h-8 rounded-md border border-input bg-background px-2"><option value="member">{t("admin.access.member")}</option><option value="admin">{t("admin.access.groupAdmin")}</option></select></div>)}</div><div className="flex gap-2"><Input aria-label={t("admin.access.inviteUsername")} value={inviteUsernames[group.id] ?? ""} onChange={(event) => setInviteUsernames((current) => ({ ...current, [group.id]: event.target.value }))} placeholder={t("admin.access.inviteUsername")} /><Button variant="outline" disabled={busy || !(inviteUsernames[group.id] ?? "").trim()} onClick={() => void inviteGroupMember(group.id)}>{t("admin.access.invite")}</Button></div></div>)}
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
      <div><h2 className="flex items-center gap-2 text-sm font-medium">{t("admin.access.shareAlbums")}</h2><p className="mt-1 text-xs text-muted-foreground">{t("admin.access.shareAlbumsHint")}</p></div>
      <div className="grid gap-2 md:grid-cols-[1fr_auto]">
        <select aria-label={t("admin.access.selectAlbum")} value={selectedAlbum} onChange={(event) => selectAlbum(event.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="">{t("admin.access.newAlbum")}</option>{albums.map((album) => <option key={album.id} value={album.id}>{album.name}</option>)}</select>
        <Button variant="outline" disabled={busy || !selectedAlbum} onClick={deleteAlbum}><Trash2 className="mr-2 h-4 w-4" />{t("admin.access.deleteAlbum")}</Button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1.5"><Label>{t("admin.access.albumName")}</Label><Input value={albumName} onChange={(event) => setAlbumName(event.target.value)} /></div>
        <div className="space-y-1.5"><Label>{t("admin.access.albumDescription")}</Label><Input value={albumDescription} onChange={(event) => setAlbumDescription(event.target.value)} /></div>
      </div>
      <div className="space-y-1.5"><Label>{t("admin.access.albumAssetKeys")}</Label><textarea aria-label={t("admin.access.albumAssetKeys")} value={albumAssetKeys} onChange={(event) => setAlbumAssetKeys(event.target.value)} placeholder={t("admin.access.albumAssetKeysHint")} className="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" /></div>
      <Button disabled={busy || !albumName.trim()} onClick={saveAlbum}>{selectedAlbum ? t("admin.access.updateAlbum") : t("admin.access.createAlbum")}</Button>
      {selectedAlbum && <div className="space-y-3 border-t border-border pt-4"><h3 className="text-sm font-medium">{t("admin.access.albumGroups")}</h3><div className="grid gap-2 sm:grid-cols-[1fr_160px_auto]"><select aria-label={t("admin.access.selectGroup")} value={albumGroup} onChange={(event) => setAlbumGroup(event.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="">{t("admin.access.selectGroup")}</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select><select aria-label={t("admin.access.permission")} value={albumPermission} onChange={(event) => setAlbumPermission(event.target.value as ShareAlbumPermission)} className="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="view">{t("admin.access.viewOnly")}</option><option value="edit">{t("admin.access.edit")}</option><option value="upload">{t("admin.access.upload")}</option></select><Button disabled={busy || !albumGroup} onClick={bindAlbumGroup}>{t("admin.access.bindAlbumGroup")}</Button></div><div className="divide-y divide-border rounded-md border border-border">{(albums.find((album) => String(album.id) === selectedAlbum)?.groups ?? []).length === 0 ? <p className="p-3 text-xs text-muted-foreground">{t("admin.access.emptyAlbumGroups")}</p> : albums.find((album) => String(album.id) === selectedAlbum)?.groups.map((binding) => <div key={binding.group_id} className="flex items-center justify-between gap-3 p-3 text-xs"><span>{binding.group_name} · {binding.permission}</span><Button variant="ghost" size="sm" disabled={busy} onClick={() => unbindAlbumGroup(binding.group_id)}>{t("admin.access.unbindAlbumGroup")}</Button></div>)}</div></div>}
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

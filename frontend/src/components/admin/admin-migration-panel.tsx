"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, Check, Copy, Database, FileJson, FolderInput, Loader2, Terminal } from "lucide-react";
import { AdminImportQueue } from "@/components/admin/admin-import-queue";
import { SegmentedControl, SyncCard, SyncNotice } from "@/components/admin/admin-sync-shared";
import { useI18n } from "@/components/providers/locale-provider";
import { useToast } from "@/components/providers/toast-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SwitchLabel } from "@/components/ui/switch-label";
import { NyaApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { MigrationConfigResponse } from "@/lib/types";

type MetadataMode = "file" | "database";
type ImportSourceType = "auto" | "nyagallery_v1" | "lsky_pro";

/** Quote a CLI argument for both PowerShell and POSIX shells when it contains spaces or quotes. */
function shellArg(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return /[\s"'`$]/.test(trimmed) ? `"${trimmed.replace(/(["`$\\])/g, "\\$1")}"` : trimmed;
}

export function AdminMigrationPanel() {
  const { t } = useI18n();
  const toast = useToast();
  const [config, setConfig] = useState<MigrationConfigResponse | null>(null);
  const [mode, setMode] = useState<MetadataMode>("database");
  const [savingMode, setSavingMode] = useState(false);
  const [restartPending, setRestartPending] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  // CLI command builder state
  const [sourceType, setSourceType] = useState<ImportSourceType>("lsky_pro");
  const [sourcePath, setSourcePath] = useState("");
  const [sourceRoot, setSourceRoot] = useState("");
  const [target, setTarget] = useState<MetadataMode>("database");
  const [outputDir, setOutputDir] = useState("");
  const [hardlink, setHardlink] = useState(false);
  const [confirmWrite, setConfirmWrite] = useState(false);
  const [convertOutput, setConvertOutput] = useState("");

  useEffect(() => {
    let cancelled = false;
    NyaApi.migrationConfig()
      .then((value) => {
        if (cancelled) return;
        setConfig(value);
        const current = value.metadata_mode === "file" ? "file" : "database";
        setMode(current);
        setTarget(current);
      })
      .catch((error) => toast.error(error instanceof Error ? error.message : t("admin.migration.loadFailed")));
    return () => {
      cancelled = true;
    };
    // toast / t are stable for the admin page lifetime
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currentMode = config?.metadata_mode === "file" ? "file" : "database";
  const modeChanged = config != null && mode !== currentMode;

  async function saveMode() {
    setSavingMode(true);
    try {
      const value = await NyaApi.updateMigrationConfig(mode);
      setConfig((current) => (current ? { ...current, metadata_mode: value.metadata_mode } : current));
      setRestartPending(Boolean(value.restart_required ?? true));
      toast.success(t("admin.migration.saved"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("admin.migration.saveFailed"));
    } finally {
      setSavingMode(false);
    }
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(value);
      window.setTimeout(() => setCopied((current) => (current === value ? null : current)), 1500);
      toast.success(t("common.copied"));
    } catch {
      toast.error(t("admin.migration.copyFailed"));
    }
  }

  const importCommand = useMemo(() => {
    const parts = ["nyagallery", "import", shellArg(sourcePath) || "<source>"];
    parts.push("--source-type", sourceType);
    if (sourceRoot.trim()) parts.push("--source-root", shellArg(sourceRoot));
    parts.push("--target", target);
    if (target === "file" && outputDir.trim()) parts.push("--output", shellArg(outputDir));
    if (hardlink) parts.push("--hardlink");
    if (confirmWrite) parts.push("--confirm");
    return parts.join(" ");
  }, [confirmWrite, hardlink, outputDir, sourcePath, sourceRoot, sourceType, target]);

  const convertCommand = useMemo(() => {
    const to: MetadataMode = currentMode === "database" ? "file" : "database";
    const parts = ["nyagallery", "convert", "--from", currentMode, "--to", to];
    if (to === "file") parts.push("--output", shellArg(convertOutput) || "<sidecar>");
    parts.push("--confirm");
    return parts.join(" ");
  }, [convertOutput, currentMode]);

  return (
    <div className="space-y-6">
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <SyncCard icon={Terminal} title={t("admin.migration.importTitle")} description={t("admin.migration.importHint")}>
          <div className="space-y-1.5">
            <Label>{t("admin.migration.sourceType")}</Label>
            <SegmentedControl
              value={sourceType}
              onChange={setSourceType}
              options={(["lsky_pro", "nyagallery_v1", "auto"] as ImportSourceType[]).map((value) => ({
                value,
                label: t(`admin.migration.sourceTypes.${value}`),
              }))}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("admin.migration.sourcePath")}</Label>
              <Input value={sourcePath} placeholder={sourceType === "lsky_pro" ? "D:\\lsky\\database.sqlite" : "export.json"} onChange={(event) => setSourcePath(event.target.value)} />
              <p className="text-[11px] text-muted-foreground">{t(`admin.migration.sourcePathHints.${sourceType}`)}</p>
            </div>
            <div className="space-y-1.5">
              <Label>{t("admin.migration.sourceRoot")}</Label>
              <Input value={sourceRoot} placeholder="D:\\lsky\\storage\\app\\uploads" onChange={(event) => setSourceRoot(event.target.value)} />
              <p className="text-[11px] text-muted-foreground">{t("admin.migration.sourceRootHint")}</p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>{t("admin.migration.target")}</Label>
              <SegmentedControl
                value={target}
                onChange={setTarget}
                options={[
                  { value: "database" as MetadataMode, label: t("admin.migration.modes.database") },
                  { value: "file" as MetadataMode, label: t("admin.migration.modes.file") },
                ]}
              />
            </div>
            {target === "file" && (
              <div className="space-y-1.5">
                <Label>{t("admin.migration.outputDir")}</Label>
                <Input value={outputDir} placeholder={t("admin.migration.outputDirPlaceholder")} onChange={(event) => setOutputDir(event.target.value)} />
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2.5 rounded-md border border-border bg-muted/35 p-3">
            <SwitchLabel label={t("admin.migration.hardlink")} checked={hardlink} onChange={setHardlink} />
            <SwitchLabel label={t("admin.migration.confirmWrite")} checked={confirmWrite} onChange={setConfirmWrite} />
          </div>
          {!confirmWrite && <SyncNotice tone="info">{t("admin.migration.dryRunHint")}</SyncNotice>}
          <CommandBox command={importCommand} copied={copied === importCommand} onCopy={() => void copy(importCommand)} disabled={!sourcePath.trim()} />
          <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.migration.runHint")}</p>
        </SyncCard>

        <aside className="space-y-6">
          <SyncCard icon={ArrowRightLeft} title={t("admin.migration.primaryTitle")} description={t("admin.migration.primaryHint")}>
            <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
              <span className="text-muted-foreground">{t("admin.migration.currentMode")}</span>
              <span className="inline-flex items-center gap-1.5 font-medium">
                {currentMode === "database" ? <Database className="h-3.5 w-3.5" /> : <FileJson className="h-3.5 w-3.5" />}
                {config ? t(`admin.migration.modes.${currentMode}`) : "…"}
              </span>
            </div>
            <SegmentedControl
              value={mode}
              onChange={setMode}
              options={[
                { value: "database" as MetadataMode, label: t("admin.migration.modes.database") },
                { value: "file" as MetadataMode, label: t("admin.migration.modes.file") },
              ]}
            />
            <Button className="w-full" disabled={!modeChanged || savingMode} onClick={() => void saveMode()}>
              {savingMode && <Loader2 className="h-4 w-4 animate-spin" />} {t("admin.migration.saveMode")}
            </Button>
            {restartPending && <SyncNotice>{t("admin.migration.restartRequired")}</SyncNotice>}
            {config && (
              <p className="break-all text-[11px] text-muted-foreground">
                {t("admin.migration.configPath")}: <code>{config.config_path}</code>
              </p>
            )}
            <div className="space-y-1.5 border-t border-border pt-3">
              <Label>{t("admin.migration.convertTitle")}</Label>
              <p className="text-[11px] leading-5 text-muted-foreground">{t("admin.migration.convertHint")}</p>
              {currentMode === "database" && (
                <Input value={convertOutput} placeholder={t("admin.migration.outputDirPlaceholder")} onChange={(event) => setConvertOutput(event.target.value)} />
              )}
              <CommandBox command={convertCommand} copied={copied === convertCommand} onCopy={() => void copy(convertCommand)} />
            </div>
          </SyncCard>

          <SyncCard icon={FolderInput} title={t("admin.migration.sourcesTitle")} description={t("admin.migration.sourcesHint")}>
            <div className="flex flex-wrap gap-1.5">
              {(config?.sources ?? []).map((source) => (
                <span key={source} className="rounded-full border border-border bg-background px-2.5 py-1 text-xs">
                  {source}
                </span>
              ))}
            </div>
          </SyncCard>
        </aside>
      </div>

      <AdminImportQueue />
    </div>
  );
}

function CommandBox({ command, copied, onCopy, disabled = false }: { command: string; copied: boolean; onCopy: () => void; disabled?: boolean }) {
  const { t } = useI18n();
  return (
    <div className={cn("flex items-start gap-2 rounded-md border border-border bg-muted/40 p-2.5", disabled && "opacity-60")}>
      <code className="min-w-0 flex-1 whitespace-pre-wrap break-all font-mono text-[11px] leading-5">{command}</code>
      <Button type="button" variant="outline" size="sm" className="h-7 shrink-0 px-2 text-xs" onClick={onCopy} disabled={disabled}>
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied ? t("common.copied") : t("admin.migration.copy")}
      </Button>
    </div>
  );
}

export type PixivTarget = {
  input: string;
  pid?: string;
  error?: "invalid" | "shortLink";
};

export type PixivTargetResult = PixivTarget & {
  status: "pending" | "running" | "success" | "error" | "invalid";
  message?: string;
};

function normalizePid(value: string): string | undefined {
  if (!/^\d+$/.test(value)) return undefined;
  const normalized = value.replace(/^0+/, "");
  return normalized || undefined;
}

export async function resolvePixivShortLink(input: string, fetcher: typeof fetch = fetch): Promise<string | undefined> {
  let current = input;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const response = await fetcher(current, { method: "HEAD", redirect: "follow" });
    const finalUrl = response.url || current;
    if (finalUrl === current) break;
    current = finalUrl;
    if (/pixiv\.net/i.test(new URL(current).hostname)) break;
  }
  const resolved = parsePixivTargets(current).find((target) => target.pid);
  return resolved?.pid;
}

export function parsePixivTargets(value: string): PixivTarget[] {
  const seen = new Set<string>();
  const targets: PixivTarget[] = [];
  for (const input of value.split(/[\s,，]+/).filter(Boolean)) {
    let pid = normalizePid(input);
    let error: PixivTarget["error"] = "invalid";
    if (!pid) {
      try {
        const url = new URL(input);
        if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password && !url.port) {
          if (url.hostname === "pixiv.me" || url.hostname === "www.pixiv.me") error = "shortLink";
          if (/(^|\.)pixiv\.net$/i.test(url.hostname) && !input.includes("\\")) {
            const artwork = url.pathname.match(/^\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?artworks\/(\d+)\/?$/i);
            if (artwork) pid = normalizePid(artwork[1]);
            else if (url.pathname === "/member_illust.php" && url.searchParams.getAll("illust_id").length === 1) {
              pid = normalizePid(url.searchParams.get("illust_id") ?? "");
            }
          }
        }
      } catch {
        // Keep invalid inputs visible alongside valid targets.
      }
    }
    const key = pid ? `pid:${pid}` : `input:${input}`;
    if (seen.has(key)) continue;
    seen.add(key);
    targets.push(pid ? { input, pid } : { input, error });
  }
  return targets;
}

export function resolvePixivSyncKind(mode: "pid" | "user", source: string, retryKind?: string): "pid" | "user" | "bookmarks" | null {
  if (retryKind !== undefined) {
    return retryKind === "pid" || retryKind === "user" || retryKind === "bookmarks" ? retryKind : null;
  }
  return mode === "pid" ? "pid" : source === "bookmarks" ? "bookmarks" : "user";
}

export function countPixivResults(results: PixivTargetResult[]) {
  return {
    total: results.length,
    success: results.filter((item) => item.status === "success").length,
    failed: results.filter((item) => item.status === "error").length,
    invalid: results.filter((item) => item.status === "invalid").length,
  };
}

export async function runPixivTargets(
  targets: PixivTarget[],
  execute: (pid: string) => Promise<string>,
  onUpdate: (results: PixivTargetResult[]) => void = () => {},
): Promise<PixivTargetResult[]> {
  const results: PixivTargetResult[] = targets.map((target) => ({ ...target, status: target.pid ? "pending" : "invalid" }));
  const publish = () => onUpdate(results.map((item) => ({ ...item })));
  publish();
  for (const item of results) {
    if (!item.pid) continue;
    item.status = "running";
    publish();
    try {
      item.message = await execute(item.pid);
      item.status = "success";
    } catch (error) {
      item.message = error instanceof Error ? error.message : String(error);
      item.status = "error";
    }
    publish();
  }
  return results;
}

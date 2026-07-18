/**
 * 115 云解压：转存后轮询离线任务，转存完成后立即解压。
 * POST /files/push_extract → GET /files/extract_info → POST /files/add_extract_file
 * 不再删除压缩包。
 */

import {
  p115Headers,
  p115HumanError,
  p115NormalizeCookie,
  p115ReadJson,
} from "@/lib/p115";

/** 轮询离线任务间隔 */
export const POLL_INTERVAL_MS = 3_000;
/** 轮询最长等待（转存就绪） */
export const POLL_MAX_MS = 30_000;

export type DeferredExtractJob = {
  cookie: string;
  folderCid: string;
  password: string;
  infoHashes?: string[];
  titleHint?: string;
};

export type ExtractRunResult = {
  ok: boolean;
  message: string;
  extracted: number;
};

type ArchiveTarget = {
  pickCode: string;
  name: string;
};

const ARCHIVE_RE = /\.(zip|rar|7z)$/i;
const scheduled = new Map<string, NodeJS.Timeout>();

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isArchiveName(name: string): boolean {
  return ARCHIVE_RE.test(name || "");
}

/** 离线任务是否已完成（可入盘 / 可解压） */
function isTaskDone(t: any): boolean {
  const status = Number(t?.status ?? -99);

  if (status === 2 || t?.status === "2") return true;
  if (Number(t?.percentDone) >= 100) return true;
  if (Number(t?.percentDone ?? t?.percent_done) >= 100) return true;

  return false;
}

/** 离线任务是否终态失败 */
function isTaskFailed(t: any): boolean {
  const status = Number(t?.status ?? 0);

  // -1 失败；其它负状态一般也表示不可继续
  return status < 0;
}

/** 与压缩包同名的文件夹名（去扩展名，去掉 115 非法字符） */
function sameNameFolderLabel(archiveName: string, titleHint?: string): string {
  let base = (archiveName || "").trim();

  if (base) {
    base = base.replace(/\.(zip|rar|7z)$/i, "");
  }
  if (!base) {
    base = (titleHint || "").trim() || "解压内容";
  }

  base = base
    .replace(/[<>"]/g, "_")
    .replace(/[/\\:*?|]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 200);

  return base || "解压内容";
}

/** 在父目录下新建同名文件夹；重名则复用已有目录 */
async function ensureSameNameFolder(
  cookie: string,
  parentCid: string,
  folderName: string,
): Promise<{ ok: true; cid: string; name: string } | { ok: false; message: string }> {
  const body = new URLSearchParams();

  body.set("pid", parentCid || "0");
  body.set("cname", folderName);

  const res = await fetch("https://webapi.115.com/files/add", {
    method: "POST",
    headers: {
      ...p115Headers(cookie),
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: body.toString(),
    cache: "no-store",
  });
  const data = await p115ReadJson(res);
  const cid = String(
    data?.cid ?? data?.file_id ?? data?.data?.cid ?? data?.data?.file_id ?? "",
  );

  if ((data?.state === true || data?.state === 1 || data?.errno === 0) && cid) {
    return { ok: true, cid, name: folderName };
  }

  try {
    const rows = await listFolderFilesOnce(cookie, parentCid);
    const hit = rows.find(
      (r) =>
        r?.cid != null &&
        !r?.fid &&
        String(r.n || r.name || "").trim() === folderName,
    );

    if (hit?.cid != null) {
      return { ok: true, cid: String(hit.cid), name: folderName };
    }
  } catch {
    // ignore
  }

  return {
    ok: false,
    message: p115HumanError(data, "创建同名文件夹失败"),
  };
}

async function listOfflineTasksOnce(cookie: string): Promise<any[]> {
  const url = new URL("https://115.com/web/lixian/");

  url.searchParams.set("ct", "lixian");
  url.searchParams.set("ac", "task_lists");
  url.searchParams.set("page", "1");

  const res = await fetch(url.toString(), {
    method: "GET",
    headers: p115Headers(cookie, "https://115.com/web/lixian/"),
    cache: "no-store",
  });
  const data = await p115ReadJson(res);
  const tasks = data?.tasks || data?.data?.tasks || data?.list || [];

  return Array.isArray(tasks) ? tasks : [];
}

async function listFolderFilesOnce(
  cookie: string,
  folderCid: string,
  limit = 100,
): Promise<any[]> {
  const url = new URL("https://webapi.115.com/files");

  url.searchParams.set("aid", "1");
  url.searchParams.set("cid", folderCid || "0");
  url.searchParams.set("o", "user_ptime");
  url.searchParams.set("asc", "0");
  url.searchParams.set("offset", "0");
  url.searchParams.set("show_dir", "1");
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("type", "0");
  url.searchParams.set("format", "json");

  const res = await fetch(url.toString(), {
    method: "GET",
    headers: p115Headers(cookie),
    cache: "no-store",
  });
  const data = await p115ReadJson(res);

  return Array.isArray(data?.data) ? data.data : [];
}

function pickCodesFromTasks(
  tasks: any[],
  infoHashes: string[],
): ArchiveTarget[] {
  const want = new Set(infoHashes.map((h) => h.toLowerCase()));
  const out: ArchiveTarget[] = [];

  for (const t of tasks) {
    const hash = String(t?.info_hash || t?.infoHash || "").toLowerCase();
    const name = String(t?.name || t?.file_name || "");
    const pick = String(t?.pick_code || t?.pickcode || t?.pc || "").trim();

    if (want.size && hash && !want.has(hash)) continue;
    if (!isTaskDone(t)) continue;
    if (pick && (isArchiveName(name) || want.has(hash))) {
      out.push({ pickCode: pick, name });
    }
  }

  return out;
}

function pickCodesFromFolder(
  rows: any[],
  titleHint?: string,
): ArchiveTarget[] {
  const hint = (titleHint || "").replace(/\s+/g, "").slice(0, 16).toLowerCase();
  const archives = rows
    .filter((r) => r?.fid && !r?.ns)
    .map((r) => ({
      pickCode: String(r.pc || r.pick_code || "").trim(),
      name: String(r.n || r.name || ""),
      time: Number(r.t || r.te || r.ptime || 0),
    }))
    .filter((r) => r.pickCode && isArchiveName(r.name));

  if (!archives.length) return [];

  if (hint) {
    const matched = archives.filter((a) =>
      a.name.toLowerCase().replace(/\s+/g, "").includes(hint.slice(0, 10)),
    );
    if (matched.length) return matched.slice(0, 3);
  }

  return archives.sort((a, b) => b.time - a.time).slice(0, 3);
}

/**
 * 轮询直到相关离线任务转存完成，并拿到可解压目标。
 * - 有 infoHashes：等待对应任务 status=完成（或目录里已出现压缩包）
 * - 无 hash：轮询目标目录出现压缩包
 */
async function waitUntilTransferReady(
  job: DeferredExtractJob,
): Promise<
  | { ok: true; targets: ArchiveTarget[] }
  | { ok: false; message: string }
> {
  const cookie = p115NormalizeCookie(job.cookie);
  const folderCid = String(job.folderCid || "0");
  const hashes = (job.infoHashes || []).map((h) => h.toLowerCase()).filter(Boolean);
  const started = Date.now();
  let lastNote = "等待离线转存完成";

  while (Date.now() - started < POLL_MAX_MS) {
    let tasks: any[] = [];

    try {
      tasks = await listOfflineTasksOnce(cookie);
    } catch (err) {
      lastNote = err instanceof Error ? err.message : "拉取离线任务失败";
      await sleep(POLL_INTERVAL_MS);
      continue;
    }

    if (hashes.length) {
      const matched = tasks.filter((t) => {
        const hash = String(t?.info_hash || t?.infoHash || "").toLowerCase();

        return hash && hashes.includes(hash);
      });

      if (matched.length) {
        const failed = matched.filter(isTaskFailed);

        if (failed.length === matched.length) {
          return { ok: false, message: "离线任务全部失败，无法解压" };
        }

        const allTerminal = matched.every((t) => isTaskDone(t) || isTaskFailed(t));
        const anyDone = matched.some(isTaskDone);

        if (anyDone && allTerminal) {
          const fromTasks = pickCodesFromTasks(tasks, hashes);

          if (fromTasks.length) {
            console.info("[p115-extract] transfer ready via tasks", {
              hashes,
              archives: fromTasks.map((t) => t.name),
            });

            return { ok: true, targets: fromTasks };
          }
        }

        if (!allTerminal) {
          const downloading = matched.find((t) => !isTaskDone(t) && !isTaskFailed(t));
          const pct = Number(
            downloading?.percentDone ?? downloading?.percent_done ?? 0,
          );

          lastNote = `转存中 ${Number.isFinite(pct) ? `${Math.floor(pct)}%` : "…"}`;
        }
      }
    }

    // 目录兜底：转存完成后压缩包会出现在目标目录
    try {
      const rows = await listFolderFilesOnce(cookie, folderCid);
      const fromFolder = pickCodesFromFolder(rows, job.titleHint);

      if (fromFolder.length) {
        // 有 hash 时，尽量等任务也到终态，避免下到一半就解压
        if (!hashes.length) {
          console.info("[p115-extract] transfer ready via folder", {
            archives: fromFolder.map((t) => t.name),
          });

          return { ok: true, targets: fromFolder };
        }

        const matched = tasks.filter((t) => {
          const hash = String(t?.info_hash || t?.infoHash || "").toLowerCase();

          return hash && hashes.includes(hash);
        });
        const allDoneOrMissing =
          !matched.length ||
          matched.every((t) => isTaskDone(t) || isTaskFailed(t));

        if (allDoneOrMissing && matched.some(isTaskDone)) {
          console.info("[p115-extract] transfer ready via folder+tasks", {
            archives: fromFolder.map((t) => t.name),
          });

          return { ok: true, targets: fromFolder };
        }
      }
    } catch {
      // ignore folder errors during poll
    }

    await sleep(POLL_INTERVAL_MS);
  }

  return {
    ok: false,
    message: `等待转存超时（${Math.round(POLL_MAX_MS / 1000)} 秒）：${lastNote}`,
  };
}

async function pushExtract(
  cookie: string,
  pickCode: string,
  password: string,
): Promise<{ ok: boolean; message: string }> {
  const body = new URLSearchParams();

  body.set("pick_code", pickCode);
  body.set("secret", password || "");

  const res = await fetch("https://webapi.115.com/files/push_extract", {
    method: "POST",
    headers: {
      ...p115Headers(cookie),
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: body.toString(),
    cache: "no-store",
  });
  const data = await p115ReadJson(res);

  if (data?.state === true || data?.state === 1 || data?.errno === 0) {
    return { ok: true, message: "已推送云解压" };
  }

  return { ok: false, message: p115HumanError(data, "推送云解压失败") };
}

async function extractInfoOnce(
  cookie: string,
  pickCode: string,
): Promise<{ files: string[]; dirs: string[]; message?: string }> {
  const url = new URL("https://webapi.115.com/files/extract_info");

  url.searchParams.set("pick_code", pickCode);
  url.searchParams.set("file_name", "");
  url.searchParams.set("next_marker", "");
  url.searchParams.set("page_count", "999");
  url.searchParams.set("paths", "文件");

  const res = await fetch(url.toString(), {
    method: "GET",
    headers: p115Headers(cookie),
    cache: "no-store",
  });
  const data = await p115ReadJson(res);

  if (data?.state === false || data?.errno) {
    return {
      files: [],
      dirs: [],
      message: p115HumanError(data, "读取压缩包目录失败（可能尚未就绪）"),
    };
  }

  const list =
    data?.data?.list || data?.list || data?.data?.files || data?.files || [];
  const files: string[] = [];
  const dirs: string[] = [];

  if (Array.isArray(list)) {
    for (const item of list) {
      const name = String(item?.file_name || item?.n || item?.name || "").trim();

      if (!name) continue;

      const isDir =
        item?.file_category === 0 ||
        item?.file_category === "0" ||
        Boolean(item?.ns) ||
        name.endsWith("/");

      if (isDir) {
        dirs.push(name.replace(/\/$/, ""));
      } else {
        files.push(name);
      }
    }
  }

  return { files, dirs };
}

async function addExtractFile(
  cookie: string,
  pickCode: string,
  toPid: string,
  files: string[],
  dirs: string[],
): Promise<{ ok: boolean; message: string }> {
  const body = new URLSearchParams();

  body.set("pick_code", pickCode);
  body.set("paths", "文件");
  body.set("to_pid", toPid || "0");

  if (!files.length && !dirs.length) {
    body.append("extract_file[]", "");
  } else {
    files.forEach((f) => body.append("extract_file[]", f));
    dirs.forEach((d) => body.append("extract_dir[]", d));
  }

  const res = await fetch("https://webapi.115.com/files/add_extract_file", {
    method: "POST",
    headers: {
      ...p115Headers(cookie),
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: body.toString(),
    cache: "no-store",
  });
  const data = await p115ReadJson(res);

  if (
    data?.state === true ||
    data?.state === 1 ||
    data?.errno === 0 ||
    data?.extract_id ||
    data?.data?.extract_id
  ) {
    return { ok: true, message: "已提交解压到目录" };
  }

  return { ok: false, message: p115HumanError(data, "解压到目录失败") };
}

/** 对已就绪的压缩包立即解压到同名子文件夹（不删除压缩包或父目录） */
async function extractReadyTargets(
  job: DeferredExtractJob,
  targets: ArchiveTarget[],
): Promise<ExtractRunResult> {
  const cookie = p115NormalizeCookie(job.cookie);
  const password = (job.password || "").trim();
  const folderCid = String(job.folderCid || "0");
  let extracted = 0;
  let lastErr = "";

  for (const t of targets) {
    const push = await pushExtract(cookie, t.pickCode, password);

    if (!push.ok) {
      lastErr = push.message;
      continue;
    }

    // 云端推送后目录可能稍晚就绪：短重试读目录，不算长时间轮询转存
    let info = await extractInfoOnce(cookie, t.pickCode);

    for (let i = 0; i < 6; i += 1) {
      if (info.files.length || info.dirs.length || !info.message) break;
      await sleep(2_000);
      info = await extractInfoOnce(cookie, t.pickCode);
    }

    if (info.message && !info.files.length && !info.dirs.length) {
      lastErr = info.message;
      continue;
    }

    const destName = sameNameFolderLabel(t.name, job.titleHint);
    const dest = await ensureSameNameFolder(cookie, folderCid, destName);

    if (!dest.ok) {
      lastErr = dest.message;
      continue;
    }

    const add = await addExtractFile(
      cookie,
      t.pickCode,
      dest.cid,
      info.files,
      info.dirs,
    );

    if (add.ok) {
      extracted += 1;
    } else {
      lastErr = add.message;
    }
  }

  if (extracted > 0) {
    return {
      ok: true,
      message: `已提交解压 ${extracted} 个压缩包到同名文件夹`,
      extracted,
    };
  }

  return { ok: false, message: lastErr || "解压未成功", extracted: 0 };
}

/** 轮询转存完成 → 立即解压（无密码压缩包 secret 可为空） */
export async function runPollThenExtract(
  job: DeferredExtractJob,
): Promise<ExtractRunResult> {
  const cookie = p115NormalizeCookie(job.cookie);

  if (!cookie) {
    return { ok: false, message: "无 Cookie", extracted: 0 };
  }

  const ready = await waitUntilTransferReady(job);

  if (!ready.ok) {
    return { ok: false, message: ready.message, extracted: 0 };
  }

  return extractReadyTargets(job, ready.targets);
}

/** @deprecated 兼容旧名；现在会先轮询转存再解压 */
export async function runDeferredExtractOnce(
  job: DeferredExtractJob,
): Promise<ExtractRunResult> {
  return runPollThenExtract(job);
}

/**
 * 后台：轮询转存完成后再解压。
 * 立即返回；不阻塞转存 API。
 */
export function scheduleDeferredExtract(
  job: DeferredExtractJob,
): { jobId: string; mode: "poll" } {
  const jobId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  // 立刻进入轮询（用 setTimeout(0) 脱离请求生命周期）
  const timer = setTimeout(() => {
    scheduled.delete(jobId);
    void runPollThenExtract(job).then((r) => {
      console.info("[p115-extract]", jobId, r.ok ? "ok" : "fail", r.message);
    });
  }, 0);

  scheduled.set(jobId, timer);
  console.info("[p115-extract] scheduled poll-then-extract", jobId, {
    hashes: job.infoHashes?.length || 0,
    folderCid: job.folderCid,
  });

  return { jobId, mode: "poll" };
}

/** 兼容旧导入（历史上曾延迟删包，已废除，切勿再接 rb/delete） */
export const EXTRACT_DELAY_MS = 0;
export const CLEANUP_DELAY_MS = 0;

/**
 * 115 云解压（单次触发，不轮询进度）。
 * POST /files/push_extract → GET /files/extract_info（一页）→ POST /files/add_extract_file
 */

import {
  p115Headers,
  p115HumanError,
  p115NormalizeCookie,
  p115ReadJson,
} from "@/lib/p115";

export const EXTRACT_DELAY_MS = 10_000;
/** 解压提交后再延迟删压缩包（给 115 云解压留读包时间，不比大小、不轮询） */
export const CLEANUP_DELAY_MS = 45_000;

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
  fileId?: string;
};

type CleanupJob = {
  cookie: string;
  parentCid: string;
  archiveName: string;
  pickCode: string;
  fileId: string;
};

const ARCHIVE_RE = /\.(zip|rar|7z)$/i;
const scheduled = new Map<string, NodeJS.Timeout>();

function isArchiveName(name: string): boolean {
  return ARCHIVE_RE.test(name || "");
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

  // 已存在等同名目录：在父目录里找一次
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
    const fileId = String(t?.file_id || t?.fid || t?.delete_file_id || "").trim();
    const status = Number(t?.status ?? -99);
    const done =
      status === 2 || Number(t?.percentDone) >= 100 || t?.status === "2";

    if (want.size && hash && !want.has(hash)) continue;
    if (!done && !pick) continue;
    if (pick && (isArchiveName(name) || want.has(hash))) {
      out.push({ pickCode: pick, name, fileId: fileId || undefined });
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
      fileId: String(r.fid || r.file_id || "").trim() || undefined,
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

async function resolveArchiveInParent(
  cookie: string,
  parentCid: string,
  pickCode: string,
  archiveName: string,
): Promise<{ fileId: string; name: string }> {
  const rows = await listFolderFilesOnce(cookie, parentCid);
  const pick = (pickCode || "").toLowerCase();
  const name = (archiveName || "").trim();

  const hit = rows.find((r) => {
    if (!r?.fid) return false;
    const pc = String(r.pc || r.pick_code || "").toLowerCase();
    const n = String(r.n || r.name || "").trim();

    return (pick && pc === pick) || (!!name && n === name);
  });

  if (!hit?.fid) {
    return { fileId: "", name };
  }

  return {
    fileId: String(hit.fid),
    name: String(hit.n || hit.name || name),
  };
}

async function deleteFileById(
  cookie: string,
  fileId: string,
  parentCid: string,
): Promise<{ ok: boolean; message: string }> {
  if (!fileId) {
    return { ok: false, message: "无文件 id，无法删除压缩包" };
  }

  const body = new URLSearchParams();

  // 115 删文件常见要 pid + fid[0]
  body.set("pid", parentCid || "0");
  body.set("fid[0]", fileId);
  body.set("ignore_warn", "1");

  const res = await fetch("https://webapi.115.com/rb/delete", {
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
    return { ok: true, message: "已删除压缩包" };
  }

  // 兼容仅 fid 形式再试一次
  const body2 = new URLSearchParams();

  body2.set("fid", fileId);
  body2.set("pid", parentCid || "0");

  const res2 = await fetch("https://webapi.115.com/rb/delete", {
    method: "POST",
    headers: {
      ...p115Headers(cookie),
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: body2.toString(),
    cache: "no-store",
  });
  const data2 = await p115ReadJson(res2);

  if (data2?.state === true || data2?.state === 1 || data2?.errno === 0) {
    return { ok: true, message: "已删除压缩包" };
  }

  return {
    ok: false,
    message: p115HumanError(data2 || data, "删除压缩包失败"),
  };
}

/** 延迟后直接删压缩包（不比对大小） */
async function runCleanupArchiveOnce(job: CleanupJob): Promise<string> {
  const cookie = p115NormalizeCookie(job.cookie);
  let fileId = (job.fileId || "").trim();

  if (!fileId) {
    const resolved = await resolveArchiveInParent(
      cookie,
      job.parentCid,
      job.pickCode,
      job.archiveName,
    );

    fileId = resolved.fileId;
  }

  if (!fileId) {
    return "跳过删包：找不到压缩包 fileId";
  }

  const del = await deleteFileById(cookie, fileId, job.parentCid);

  console.info("[p115-cleanup] delete", {
    fileId,
    parentCid: job.parentCid,
    ok: del.ok,
    message: del.message,
  });

  return del.message;
}

function scheduleCleanupArchive(job: CleanupJob, delayMs = CLEANUP_DELAY_MS) {
  const jobId = `clean_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
  const wait = Math.max(1000, delayMs);
  const timer = setTimeout(() => {
    scheduled.delete(jobId);
    void runCleanupArchiveOnce(job).then((msg) => {
      console.info("[p115-cleanup]", jobId, msg);
    });
  }, wait);

  scheduled.set(jobId, timer);
  console.info("[p115-cleanup] scheduled", jobId, `in ${wait}ms`, {
    fileId: job.fileId,
    pickCode: job.pickCode,
  });
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

/** 单次解压尝试：不轮询进度 */
export async function runDeferredExtractOnce(
  job: DeferredExtractJob,
): Promise<ExtractRunResult> {
  const cookie = p115NormalizeCookie(job.cookie);
  const password = (job.password || "").trim();
  const folderCid = String(job.folderCid || "0");

  if (!cookie) {
    return { ok: false, message: "无 Cookie", extracted: 0 };
  }
  if (!password) {
    return { ok: false, message: "无解压密码", extracted: 0 };
  }

  let targets: ArchiveTarget[] = [];

  try {
    const tasks = await listOfflineTasksOnce(cookie);

    targets = pickCodesFromTasks(tasks, job.infoHashes || []);
  } catch {
    // 走目录兜底
  }

  if (!targets.length) {
    try {
      const rows = await listFolderFilesOnce(cookie, folderCid);

      targets = pickCodesFromFolder(rows, job.titleHint);
    } catch (err) {
      return {
        ok: false,
        message: err instanceof Error ? err.message : "定位压缩包失败",
        extracted: 0,
      };
    }
  }

  if (!targets.length) {
    return {
      ok: false,
      message: "延时触发时未找到可解压压缩包（可能仍在云下载）",
      extracted: 0,
    };
  }

  let extracted = 0;
  let lastErr = "";

  for (const t of targets) {
    const push = await pushExtract(cookie, t.pickCode, password);

    if (!push.ok) {
      lastErr = push.message;
      continue;
    }

    const info = await extractInfoOnce(cookie, t.pickCode);

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

      // 提交解压时钉死 fileId，延迟后直接删包（不比大小）
      let fileId = (t.fileId || "").trim();
      let archiveName = t.name;

      if (!fileId) {
        const resolved = await resolveArchiveInParent(
          cookie,
          folderCid,
          t.pickCode,
          t.name,
        );

        fileId = resolved.fileId;
        if (resolved.name) archiveName = resolved.name;
      }

      if (fileId) {
        scheduleCleanupArchive({
          cookie,
          parentCid: folderCid,
          archiveName,
          pickCode: t.pickCode,
          fileId,
        });
      } else {
        console.warn(
          "[p115-cleanup] skip schedule: no fileId for",
          t.pickCode,
          t.name,
        );
      }
    } else {
      lastErr = add.message;
    }
  }

  if (extracted > 0) {
    return {
      ok: true,
      message: `已提交解压 ${extracted} 个压缩包到同名文件夹（稍后删除压缩包）`,
      extracted,
    };
  }

  return { ok: false, message: lastErr || "解压未成功", extracted: 0 };
}

/** 转存成功后延迟一次触发（默认 10s），不轮询 */
export function scheduleDeferredExtract(
  job: DeferredExtractJob,
  delayMs = EXTRACT_DELAY_MS,
): { jobId: string; delayMs: number } {
  const jobId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const wait = Math.max(1000, delayMs);
  const timer = setTimeout(() => {
    scheduled.delete(jobId);
    void runDeferredExtractOnce(job).then((r) => {
      console.info("[p115-extract]", jobId, r.ok ? "ok" : "fail", r.message);
    });
  }, wait);

  scheduled.set(jobId, timer);

  return { jobId, delayMs: wait };
}

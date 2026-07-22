/**
 * 115 云下载客户端（Cookie 模拟网页）。
 *
 * 参考成熟项目实现路径：
 * - 经典离线：GET ?ct=offline&ac=space → POST /web/lixian/?ct=lixian&ac=add_task_url(s)
 *   （七味、the-115-api、115wangpan 系）
 * - 回退：POST https://clouddownload.115.com/web/?ac=add_task_url(s)
 *   （p115client / 部分网页客户端）
 * - 目录：GET webapi.115.com/files（CloudSaver）
 *
 * 不实现 115driver 的 lixianssp RSA 加密接口（依赖私有密钥，个人前端不划算）。
 */

export type P115AddResult = {
  ok: boolean;
  message: string;
  added: number;
  failed: { url: string; message: string }[];
  infoHashes?: string[];
  raw?: unknown;
};

export type P115ValidateResult = {
  ok: boolean;
  message: string;
  userId?: string;
  folderCid?: string;
  folderName?: string;
  quota?: number | null;
  quotaTotal?: number | null;
};

export type P115FolderItem = {
  cid: string;
  name: string;
};

export type P115FolderListResult = {
  ok: boolean;
  message: string;
  parentCid: string;
  path: { cid: string; name: string }[];
  folders: P115FolderItem[];
};

type OfflineSign = {
  sign: string;
  time: string;
  quota: number | null;
  quotaTotal: number | null;
};

const BATCH_LIMIT = 15;
const REQUEST_GAP_MS = 400;

const ERRCODE_HINT: Record<number, string> = {
  911: "需要验证码，请先在 115 网页云下载页通过后再试",
  10008: "任务已存在",
  10004: "链接无效或不支持",
  10007: "空间不足",
  10009: "离线任务配额已满",
  [-1]: "Cookie 无效或已过期",
};

export function p115NormalizeCookie(cookie: string): string {
  return cookie
    .trim()
    .replace(/\r?\n/g, "; ")
    .replace(/;{2,}/g, "; ")
    .replace(/^;+|;\s*$/g, "");
}

function normalizeCookie(cookie: string): string {
  return p115NormalizeCookie(cookie);
}

function cookiePart(cookie: string, key: string): string {
  const m = normalizeCookie(cookie).match(
    new RegExp(`(?:^|;\\s*)${key}=([^;]+)`, "i"),
  );

  return (m?.[1] || "").trim();
}

/** UID Cookie 形如 `12345_A1_...`，取前导数字作离线 uid */
function extractUid(cookie: string): string {
  const raw = cookiePart(cookie, "UID");
  const m = raw.match(/^(\d+)/);

  return m?.[1] || raw || "";
}

function requireCookieParts(cookie: string): string | null {
  const c = normalizeCookie(cookie);
  const need = ["UID", "CID", "SEID"];

  for (const key of need) {
    if (!new RegExp(`(?:^|;\\s*)${key}=`, "i").test(c)) {
      return `Cookie 缺少 ${key}（需含 UID / CID / SEID，建议含 KID）`;
    }
  }

  return null;
}

export function p115Headers(
  cookie: string,
  referer = "https://115.com/",
): HeadersInit {
  return {
    Cookie: normalizeCookie(cookie),
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    Accept: "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
    Origin: "https://115.com",
    Referer: referer,
    "X-Requested-With": "XMLHttpRequest",
  };
}

function commonHeaders(cookie: string, referer = "https://115.com/"): HeadersInit {
  return p115Headers(cookie, referer);
}

export async function p115ReadJson(res: Response): Promise<any> {
  const text = await res.text();

  try {
    return JSON.parse(text);
  } catch {
    return { state: false, error: text.slice(0, 240) || `HTTP ${res.status}` };
  }
}

async function readJsonSafe(res: Response): Promise<any> {
  return p115ReadJson(res);
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

export function p115HumanError(data: any, fallback = "操作失败"): string {
  const code = Number(data?.errcode ?? data?.errno ?? data?.error_code ?? NaN);
  if (Number.isFinite(code) && ERRCODE_HINT[code]) {
    return ERRCODE_HINT[code];
  }

  const msg = String(
    data?.error_msg ||
      data?.error ||
      data?.message ||
      data?.msg ||
      data?.errMsg ||
      "",
  ).trim();

  if (/验证码|captcha|911/i.test(msg)) {
    return ERRCODE_HINT[911];
  }
  if (/空间不足|quota|配额/i.test(msg)) {
    return msg || ERRCODE_HINT[10009];
  }

  return msg || fallback;
}

function humanError(data: any, fallback = "操作失败"): string {
  return p115HumanError(data, fallback);
}

/** 从离线添加响应里提取 info_hash（用于延时解压定位任务） */
export function collectInfoHashes(raw: unknown): string[] {
  const out = new Set<string>();
  const dig = (node: any) => {
    if (!node) return;
    if (typeof node === "string" && /^[a-f0-9]{32,40}$/i.test(node)) {
      out.add(node.toLowerCase());

      return;
    }
    if (Array.isArray(node)) {
      node.forEach(dig);

      return;
    }
    if (typeof node !== "object") return;
    const h = node.info_hash || node.infoHash || node.hash;
    if (typeof h === "string" && h.length >= 32) {
      out.add(h.toLowerCase());
    }
    if (node.result) dig(node.result);
    if (node.data) dig(node.data);
  };

  dig(raw);

  return Array.from(out);
}

function isAddOk(data: any): boolean {
  if (!data || typeof data !== "object") return false;
  if (data.state === true || data.state === 1) return true;
  if (data.errcode === 0 || data.errno === 0) return true;
  if (data.info_hash || data.data?.info_hash) return true;
  if (Array.isArray(data.result)) {
    return data.result.some(
      (row: any) =>
        row &&
        (row.state === true ||
          row.errcode === 0 ||
          row.info_hash ||
          (!row.error_msg && !row.error)),
    );
  }

  return false;
}

/** 拉取离线签名 + 配额（成熟链路必需的一步） */
export async function fetchOfflineSign(
  cookie: string,
): Promise<{ ok: true; data: OfflineSign } | { ok: false; message: string }> {
  try {
    const res = await fetch("https://115.com/?ct=offline&ac=space", {
      method: "GET",
      headers: commonHeaders(cookie, "https://115.com/web/lixian/"),
      cache: "no-store",
    });
    const data = await readJsonSafe(res);

    if (data?.state === false || (!data?.sign && data?.errno)) {
      return {
        ok: false,
        message: humanError(data, "获取离线签名失败（Cookie 可能过期）"),
      };
    }

    const sign = String(data?.sign || "").trim();
    const time = String(data?.time ?? "").trim();

    if (!sign || !time) {
      return {
        ok: false,
        message: humanError(data, "离线签名为空，请重新登录 115 复制 Cookie"),
      };
    }

    return {
      ok: true,
      data: {
        sign,
        time,
        quota:
          data?.data?.count != null
            ? Number(data.data.count)
            : data?.quota != null
              ? Number(data.quota)
              : null,
        quotaTotal:
          data?.data?.size != null
            ? Number(data.data.size)
            : data?.quota_total != null
              ? Number(data.quota_total)
              : null,
      },
    };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "获取离线签名失败",
    };
  }
}

/** 校验 Cookie，并确认目标目录；顺带测离线签名 */
export async function validateP115(
  cookie: string,
  folderCid = "0",
): Promise<P115ValidateResult> {
  const bad = requireCookieParts(cookie);

  if (bad) {
    return { ok: false, message: bad };
  }

  const cid = String(folderCid || "0").trim() || "0";
  const url = new URL("https://webapi.115.com/files");

  url.searchParams.set("aid", "1");
  url.searchParams.set("cid", cid);
  url.searchParams.set("o", "user_ptime");
  url.searchParams.set("asc", "1");
  url.searchParams.set("offset", "0");
  url.searchParams.set("show_dir", "1");
  url.searchParams.set("limit", "1");
  url.searchParams.set("type", "0");
  url.searchParams.set("format", "json");

  try {
    const res = await fetch(url.toString(), {
      method: "GET",
      headers: commonHeaders(cookie),
      cache: "no-store",
    });
    const data = await readJsonSafe(res);

    if (data?.state === false || data?.errno) {
      return {
        ok: false,
        message: humanError(data, "Cookie 无效或已过期"),
      };
    }

    const pathArr = Array.isArray(data?.path) ? data.path : [];
    const last = pathArr[pathArr.length - 1];
    const folderName =
      cid === "0"
        ? "根目录"
        : String(
            last?.name || last?.n || data?.name || data?.current?.name || `CID ${cid}`,
          );

    const signRes = await fetchOfflineSign(cookie);
    const uid = extractUid(cookie);

    if (!signRes.ok) {
      return {
        ok: true,
        message: `目录可读，但离线签名失败：${signRes.message}`,
        userId: uid,
        folderCid: cid,
        folderName,
      };
    }

    return {
      ok: true,
      message: "连通正常（目录 + 离线签名）",
      userId: uid,
      folderCid: cid,
      folderName,
      quota: signRes.data.quota,
      quotaTotal: signRes.data.quotaTotal,
    };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "请求 115 失败",
    };
  }
}

/** 列子目录，便于选转存 CID（CloudSaver 同款） */
export async function listFolders(
  cookie: string,
  parentCid = "0",
): Promise<P115FolderListResult> {
  const bad = requireCookieParts(cookie);

  if (bad) {
    return {
      ok: false,
      message: bad,
      parentCid: "0",
      path: [],
      folders: [],
    };
  }

  const cid = String(parentCid || "0").trim() || "0";
  const url = new URL("https://webapi.115.com/files");

  url.searchParams.set("aid", "1");
  url.searchParams.set("cid", cid);
  url.searchParams.set("o", "user_ptime");
  url.searchParams.set("asc", "1");
  url.searchParams.set("offset", "0");
  url.searchParams.set("show_dir", "1");
  url.searchParams.set("limit", "100");
  url.searchParams.set("type", "0");
  url.searchParams.set("format", "json");
  url.searchParams.set("star", "0");
  url.searchParams.set("natsort", "0");
  url.searchParams.set("fc_mix", "0");

  try {
    const res = await fetch(url.toString(), {
      method: "GET",
      headers: commonHeaders(cookie),
      cache: "no-store",
    });
    const data = await readJsonSafe(res);

    if (data?.state === false || data?.errno) {
      return {
        ok: false,
        message: humanError(data, "获取目录失败"),
        parentCid: cid,
        path: [],
        folders: [],
      };
    }

    const rows = Array.isArray(data?.data) ? data.data : [];
    // 目录：有 cid、无 fid；ns 为子项数（空目录可能为 0，不可用 !!ns）
    const folders: P115FolderItem[] = rows
      .filter(
        (item: any) =>
          item?.cid != null &&
          String(item.cid) !== "" &&
          !item.fid &&
          !item.sha,
      )
      .map((item: any) => ({
        cid: String(item.cid),
        name: String(item.n || item.name || item.cid),
      }));

    const pathRaw = Array.isArray(data?.path) ? data.path : [];
    const path = pathRaw.map((p: any) => ({
      cid: String(p.cid ?? p.file_id ?? "0"),
      name: String(p.name || p.n || "根目录"),
    }));

    return {
      ok: true,
      message: "ok",
      parentCid: cid,
      path: path.length ? path : [{ cid: "0", name: "根目录" }],
      folders,
    };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "获取目录失败",
      parentCid: cid,
      path: [],
      folders: [],
    };
  }
}

type AddAttempt = { ok: boolean; message: string; raw?: unknown; perUrl?: { url: string; message: string }[] };

async function addViaLixian(
  cookie: string,
  urls: string[],
  folderCid: string,
  sign: OfflineSign,
): Promise<AddAttempt> {
  const uid = extractUid(cookie);
  const body = new URLSearchParams();

  body.set("uid", uid);
  body.set("sign", sign.sign);
  body.set("time", sign.time);
  body.set("wp_path_id", folderCid);

  const multi = urls.length > 1;
  const endpoint = multi
    ? "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
    : "https://115.com/web/lixian/?ct=lixian&ac=add_task_url";

  if (multi) {
    urls.forEach((u, i) => body.set(`url[${i}]`, u));
  } else {
    body.set("url", urls[0]);
  }

  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      ...commonHeaders(cookie, "https://115.com/web/lixian/"),
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: body.toString(),
    cache: "no-store",
  });
  const data = await readJsonSafe(res);

  if (isAddOk(data)) {
    const perUrl: { url: string; message: string }[] = [];

    if (Array.isArray(data?.result)) {
      data.result.forEach((row: any, i: number) => {
        const u = String(row?.url || urls[i] || "");
        if (row?.error_msg || (row?.state === false && !row?.info_hash)) {
          perUrl.push({ url: u, message: humanError(row, "添加失败") });
        }
      });
    }

    if (perUrl.length && perUrl.length >= urls.length) {
      return { ok: false, message: perUrl[0].message, raw: data, perUrl };
    }

    return {
      ok: true,
      message: multi ? `已提交 ${urls.length} 条到云下载` : "已加入云下载",
      raw: data,
      perUrl,
    };
  }

  return { ok: false, message: humanError(data, "lixian 添加失败"), raw: data };
}

async function addViaCloudDownload(
  cookie: string,
  urls: string[],
  folderCid: string,
): Promise<AddAttempt> {
  const body = new URLSearchParams();
  const multi = urls.length > 1;

  body.set("ac", multi ? "add_task_urls" : "add_task_url");
  body.set("wp_path_id", folderCid);

  if (multi) {
    urls.forEach((u, i) => body.set(`url[${i}]`, u));
  } else {
    body.set("url", urls[0]);
  }

  const res = await fetch("https://clouddownload.115.com/web/", {
    method: "POST",
    headers: {
      ...commonHeaders(cookie, "https://115.com/"),
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: body.toString(),
    cache: "no-store",
  });
  const data = await readJsonSafe(res);

  if (isAddOk(data)) {
    return {
      ok: true,
      message: multi ? `已提交 ${urls.length} 条到云下载` : "已加入云下载",
      raw: data,
    };
  }

  return {
    ok: false,
    message: humanError(data, "clouddownload 添加失败"),
    raw: data,
  };
}

async function addUrlChunk(
  cookie: string,
  urls: string[],
  folderCid: string,
  sign: OfflineSign | null,
): Promise<AddAttempt> {
  if (sign) {
    const primary = await addViaLixian(cookie, urls, folderCid, sign);

    if (primary.ok) return primary;
    // 签名类失败别盲回退；其它错误可试 clouddownload
    if (/签名|Cookie|过期|验证码|911|配额|空间不足/i.test(primary.message)) {
      return primary;
    }
  }

  return addViaCloudDownload(cookie, urls, folderCid);
}

export async function addOfflineTasks(
  cookie: string,
  urls: string[],
  folderCid = "0",
): Promise<P115AddResult> {
  const bad = requireCookieParts(cookie);

  if (bad) {
    return { ok: false, message: bad, added: 0, failed: [] };
  }

  const cleaned = Array.from(
    new Set(
      urls
        .map((u) => (u || "").trim())
        .filter((u) => {
          const s = (u || "").trim();
          if (!/^(magnet:|ed2k:\/\/|https?:\/\/|ftp:\/\/)/i.test(s)) {
            return false;
          }
          // 分享页走 share/receive，不进离线云下载
          const low = s.toLowerCase();
          if (low.includes("115cdn.com/s/") || low.includes("115.com/s/")) {
            return false;
          }
          return true;
        }),
    ),
  );

  if (!cleaned.length) {
    return { ok: false, message: "没有可转存的磁力/ED2K/HTTP 链接", added: 0, failed: [] };
  }

  const cid = String(folderCid || "0").trim() || "0";
  const signRes = await fetchOfflineSign(cookie);
  const sign = signRes.ok ? signRes.data : null;

  if (!signRes.ok && cleaned.length) {
    // 仍尝试 clouddownload 回退
  }

  const failed: { url: string; message: string }[] = [];
  const infoHashes = new Set<string>();
  let added = 0;

  // 经典接口单次最多约 15 条
  for (let i = 0; i < cleaned.length; i += BATCH_LIMIT) {
    const chunk = cleaned.slice(i, i + BATCH_LIMIT);

    try {
      const attempt = await addUrlChunk(cookie, chunk, cid, sign);

      if (attempt.ok) {
        collectInfoHashes(attempt.raw).forEach((h) => infoHashes.add(h));
        const chunkFailed = attempt.perUrl || [];

        added += chunk.length - chunkFailed.length;
        failed.push(...chunkFailed);
      } else if (chunk.length === 1) {
        failed.push({ url: chunk[0], message: attempt.message });
      } else {
        // 批量整段失败 → 逐条
        for (const url of chunk) {
          try {
            const one = await addUrlChunk(cookie, [url], cid, sign);

            if (one.ok) {
              added += 1;
              collectInfoHashes(one.raw).forEach((h) => infoHashes.add(h));
            } else {
              failed.push({ url, message: one.message });
            }
          } catch (err) {
            failed.push({
              url,
              message: err instanceof Error ? err.message : "请求失败",
            });
          }
          await sleep(REQUEST_GAP_MS);
        }
      }
    } catch (err) {
      for (const url of chunk) {
        failed.push({
          url,
          message: err instanceof Error ? err.message : "请求失败",
        });
      }
    }

    if (i + BATCH_LIMIT < cleaned.length) {
      await sleep(REQUEST_GAP_MS);
    }
  }

  const hashes = Array.from(infoHashes);

  if (added > 0 && failed.length === 0) {
    return {
      ok: true,
      message: `已转存 ${added} 条到 115 云下载`,
      added,
      failed,
      infoHashes: hashes,
    };
  }

  if (added > 0) {
    return {
      ok: true,
      message: `转存完成：成功 ${added} · 失败 ${failed.length}${
        failed[0] ? `（例：${failed[0].message}）` : ""
      }`,
      added,
      failed,
      infoHashes: hashes,
    };
  }

  return {
    ok: false,
    message:
      failed[0]?.message ||
      (signRes.ok ? "转存失败" : signRes.message) ||
      "转存失败",
    added: 0,
    failed,
    infoHashes: hashes,
  };
}

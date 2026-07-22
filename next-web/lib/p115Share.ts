/**
 * 115 分享链接转存（share/snap + share/receive）。
 * 与离线磁力/电驴通道分离。
 */

import {
  p115Headers,
  p115HumanError,
  p115NormalizeCookie,
  p115ReadJson,
} from "@/lib/p115";

export type Parsed115Share = {
  shareCode: string;
  receiveCode: string;
  host: string;
  url: string;
};

export type P115ShareReceiveResult = {
  ok: boolean;
  message: string;
  received: number;
  failed: { url: string; message: string }[];
};

const SHARE_URL_RE =
  /(?:https?:\/\/)?(?:www\.)?(115cdn\.com|115\.com)\/s\/([A-Za-z0-9]+)(?:\?([^\s#]*))?/i;

function cookiePart(cookie: string, key: string): string {
  const m = p115NormalizeCookie(cookie).match(
    new RegExp(`(?:^|;\\s*)${key}=([^;]+)`, "i"),
  );

  return (m?.[1] || "").trim();
}

function extractUid(cookie: string): string {
  const raw = cookiePart(cookie, "UID");
  const m = raw.match(/^(\d+)/);

  return m?.[1] || raw || "";
}

function queryParam(query: string, key: string): string {
  if (!query) return "";
  const q = query.startsWith("?") ? query.slice(1) : query;
  try {
    const params = new URLSearchParams(q);
    return (
      params.get(key) ||
      params.get(key.toUpperCase()) ||
      params.get(key.toLowerCase()) ||
      ""
    ).trim();
  } catch {
    return "";
  }
}

export function is115ShareLink(link?: string | null): boolean {
  const lower = (link || "").trim().toLowerCase();
  return lower.includes("115cdn.com/s/") || lower.includes("115.com/s/");
}

export function parse115ShareUrl(
  link: string,
  fallbackPassword = "",
): Parsed115Share | null {
  const raw = (link || "").trim();
  if (!raw) return null;
  const m = raw.match(SHARE_URL_RE);
  if (!m) return null;
  const host = (m[1] || "115cdn.com").toLowerCase();
  const shareCode = (m[2] || "").trim();
  if (!shareCode) return null;
  const receiveCode =
    queryParam(m[3] || "", "password") ||
    queryParam(m[3] || "", "pwd") ||
    queryParam(m[3] || "", "passwd") ||
    (fallbackPassword || "").trim();
  const url = receiveCode
    ? `https://${host}/s/${shareCode}?password=${receiveCode}`
    : `https://${host}/s/${shareCode}`;
  return { shareCode, receiveCode, host, url };
}

function shareReferer(share: Parsed115Share): string {
  return `https://${share.host}/s/${share.shareCode}?password=${share.receiveCode || ""}&`;
}

type ShareListItem = {
  fid?: string | number;
  cid?: string | number;
  file_id?: string | number;
  file_name?: string;
  n?: string;
  s?: number;
};

async function fetchShareSnap(
  cookie: string,
  share: Parsed115Share,
  cid = "0",
  offset = 0,
  limit = 100,
): Promise<{ ok: boolean; message: string; list: ShareListItem[]; count: number }> {
  const url = new URL("https://webapi.115.com/share/snap");
  url.searchParams.set("share_code", share.shareCode);
  url.searchParams.set("receive_code", share.receiveCode || "");
  url.searchParams.set("cid", cid);
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("offset", String(offset));
  url.searchParams.set("format", "json");

  try {
    const res = await fetch(url.toString(), {
      method: "GET",
      headers: p115Headers(cookie, shareReferer(share)),
      cache: "no-store",
    });
    const data = await p115ReadJson(res);
    if (!data?.state) {
      return {
        ok: false,
        message: p115HumanError(data, "读取分享内容失败"),
        list: [],
        count: 0,
      };
    }
    const list = Array.isArray(data?.data?.list) ? data.data.list : [];
    const count = Number(data?.data?.count ?? list.length) || list.length;
    return { ok: true, message: "ok", list, count };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "读取分享内容失败",
      list: [],
      count: 0,
    };
  }
}

async function listAllShareRootItems(
  cookie: string,
  share: Parsed115Share,
): Promise<{ ok: boolean; message: string; fileIds: string[] }> {
  const fileIds: string[] = [];
  let offset = 0;
  const limit = 100;
  let total = Infinity;

  while (offset < total && offset < 2000) {
    const page = await fetchShareSnap(cookie, share, "0", offset, limit);
    if (!page.ok) {
      return { ok: false, message: page.message, fileIds: [] };
    }
    total = page.count || page.list.length;
    for (const item of page.list) {
      const id = String(item.fid ?? item.file_id ?? item.cid ?? "").trim();
      if (id && id !== "0") fileIds.push(id);
    }
    if (!page.list.length) break;
    offset += page.list.length;
    if (page.list.length < limit) break;
  }

  // 去重
  const unique = Array.from(new Set(fileIds));
  if (!unique.length) {
    return { ok: false, message: "分享内容为空或无法读取文件列表", fileIds: [] };
  }
  return { ok: true, message: "ok", fileIds: unique };
}

async function postShareReceive(
  cookie: string,
  share: Parsed115Share,
  fileIds: string[],
  folderCid: string,
): Promise<{ ok: boolean; message: string }> {
  const uid = extractUid(cookie);
  if (!uid) {
    return { ok: false, message: "Cookie 缺少 UID" };
  }
  const body = new URLSearchParams();
  body.set("user_id", uid);
  body.set("share_code", share.shareCode);
  body.set("receive_code", share.receiveCode || "");
  body.set("file_id", fileIds.join(","));
  if (folderCid && folderCid !== "0") {
    body.set("cid", folderCid);
  }

  try {
    const res = await fetch("https://webapi.115.com/share/receive", {
      method: "POST",
      headers: {
        ...p115Headers(cookie, shareReferer(share)),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
      },
      body: body.toString(),
      cache: "no-store",
    });
    const data = await p115ReadJson(res);
    if (data?.state) {
      return { ok: true, message: "分享已转存到网盘" };
    }
    const err = p115HumanError(data, "分享转存失败");
    // 已接收过：视为成功
    if (/无需重复接收|已经接收|已接收/.test(err)) {
      return { ok: true, message: "分享已在网盘中（无需重复接收）" };
    }
    return { ok: false, message: err };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "分享转存请求失败",
    };
  }
}

/** 批量转存 115 分享链接到指定目录 */
export async function receive115Shares(
  cookieRaw: string,
  urls: string[],
  folderCid = "0",
  fallbackPassword = "",
): Promise<P115ShareReceiveResult> {
  const cookie = p115NormalizeCookie(cookieRaw);
  if (!cookie) {
    return { ok: false, message: "Cookie 为空", received: 0, failed: [] };
  }

  const failed: { url: string; message: string }[] = [];
  let received = 0;
  const seen = new Set<string>();

  for (const raw of urls) {
    const share = parse115ShareUrl(raw, fallbackPassword);
    if (!share) {
      failed.push({ url: raw, message: "不是有效的 115 分享链接" });
      continue;
    }
    const key = `${share.host}/${share.shareCode}`.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);

    const listed = await listAllShareRootItems(cookie, share);
    if (!listed.ok) {
      failed.push({ url: share.url, message: listed.message });
      continue;
    }

    const result = await postShareReceive(
      cookie,
      share,
      listed.fileIds,
      folderCid || "0",
    );
    if (result.ok) {
      received += 1;
    } else {
      failed.push({ url: share.url, message: result.message });
    }
  }

  if (received > 0 && failed.length === 0) {
    return {
      ok: true,
      message: `已转存 ${received} 个 115 分享到网盘`,
      received,
      failed,
    };
  }
  if (received > 0) {
    return {
      ok: true,
      message: `转存完成：成功 ${received} · 失败 ${failed.length}`,
      received,
      failed,
    };
  }
  return {
    ok: false,
    message: failed[0]?.message || "分享转存失败",
    received: 0,
    failed,
  };
}

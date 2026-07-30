import { Agent, fetch as undiciFetch } from "undici";

import { getActiveProxy } from "./proxy.js";

/** FlareSolverr /v1 地址；空=未启用（对齐 mdc-ng metadata.flaresolverr） */
let activeFlareUrl = "";

const directAgent = new Agent();

export function applyFlareSolverr(url: string | null | undefined): void {
  const trimmed = String(url || "").trim().replace(/\/+$/, "");
  // 允许填 http://host:8191 或 .../v1
  if (!trimmed) {
    activeFlareUrl = "";
    console.log("[scrape-web] flaresolverr cleared");
    return;
  }
  activeFlareUrl = /\/v1$/i.test(trimmed) ? trimmed : `${trimmed}/v1`;
  console.log(`[scrape-web] flaresolverr ${activeFlareUrl}`);
}

export function getFlareSolverrUrl(): string {
  if (activeFlareUrl) return activeFlareUrl;
  const env = String(process.env.FLARESOLVERR_URL || "").trim();
  if (!env) return "";
  return /\/v1$/i.test(env) ? env.replace(/\/+$/, "") : `${env.replace(/\/+$/, "")}/v1`;
}

function cookieHeaderToFsCookies(
  cookieHeader: string | undefined,
): Array<{ name: string; value: string }> | undefined {
  const raw = String(cookieHeader || "").trim();
  if (!raw) return undefined;
  const out: Array<{ name: string; value: string }> = [];
  for (const part of raw.split(";")) {
    const idx = part.indexOf("=");
    if (idx <= 0) continue;
    const name = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (name) out.push({ name, value });
  }
  return out.length ? out : undefined;
}

/**
 * 经 FlareSolverr 取 HTML（过 Cloudflare）。
 * proxy 必须用 { url } 对象，不能传字符串（mdc-ng issue #465）。
 */
export async function fetchViaFlareSolverr(
  targetUrl: string,
  opts?: {
    timeoutMs?: number;
    /** 是否把全局代理传给 FS 浏览器；默认跟随 getActiveProxy */
    useProxy?: boolean;
    cookie?: string;
  },
): Promise<string> {
  const flare = getFlareSolverrUrl();
  if (!flare) throw new Error("flaresolverr not configured");

  const maxTimeout = Math.max(
    15000,
    opts?.timeoutMs || Number(process.env.FLARESOLVERR_TIMEOUT_MS || 60000),
  );

  const body: Record<string, unknown> = {
    cmd: "request.get",
    url: targetUrl,
    maxTimeout,
  };

  const useProxy = opts?.useProxy !== false;
  const proxy = useProxy ? getActiveProxy() : "";
  if (proxy) {
    // 正确格式：对象，不是字符串
    body.proxy = { url: proxy };
  }

  const cookies = cookieHeaderToFsCookies(opts?.cookie);
  if (cookies) body.cookies = cookies;

  const res = await undiciFetch(flare, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    redirect: "follow",
    signal: AbortSignal.timeout(maxTimeout + 15000),
    // FS 本机服务：直连，不走刮削代理
    dispatcher: directAgent,
  });

  const text = await res.text();
  let json: {
    status?: string;
    message?: string;
    solution?: { response?: string; status?: number };
  };
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`flaresolverr bad json HTTP ${res.status}`);
  }
  if (!res.ok || json.status !== "ok") {
    throw new Error(
      json.message || `flaresolverr failed HTTP ${res.status}`,
    );
  }
  const html = json.solution?.response;
  if (!html) throw new Error("flaresolverr empty response");
  const st = json.solution?.status;
  if (st && st >= 400) {
    throw new Error(`flaresolverr target HTTP ${st} ${targetUrl}`);
  }
  return html;
}

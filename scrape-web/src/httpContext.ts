import { AsyncLocalStorage } from "node:async_hooks";
import { Agent, ProxyAgent, type Dispatcher, type RequestInit } from "undici";

import { getActiveProxy } from "./proxy.js";

export type ProxyMode = "inherit" | "on" | "off";

const DEFAULT_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36";

/** 当前刮削源的请求画像（Cookie / UA / 代理 / 超时 / 重试 / FS） */
export type RequestProfile = {
  cookie?: string;
  userAgent?: string;
  proxyMode?: ProxyMode;
  timeoutMs?: number;
  retry?: number;
  referer?: string;
  useFlareSolverr?: boolean;
};

const store = new AsyncLocalStorage<RequestProfile>();

export function profileFromSource(cfg: {
  cookie?: string;
  userAgent?: string;
  proxyMode?: ProxyMode;
  timeoutMs?: number;
  retry?: number;
  useFlareSolverr?: boolean;
}): RequestProfile {
  return {
    cookie: cfg.cookie || undefined,
    userAgent: cfg.userAgent || undefined,
    proxyMode: cfg.proxyMode || "inherit",
    timeoutMs: cfg.timeoutMs && cfg.timeoutMs > 0 ? cfg.timeoutMs : undefined,
    retry: cfg.retry ?? 1,
    useFlareSolverr: Boolean(cfg.useFlareSolverr),
  };
}

export function runWithRequestProfile<T>(
  profile: RequestProfile,
  fn: () => Promise<T>,
): Promise<T> {
  return store.run(profile, fn);
}

export function getRequestProfile(): RequestProfile {
  return store.getStore() || {};
}

let directAgent: Agent | null = null;
const proxyAgents = new Map<string, ProxyAgent>();

function dispatcherFor(mode: ProxyMode | undefined): Dispatcher | undefined {
  const m = mode || "inherit";
  if (m === "off") {
    if (!directAgent) directAgent = new Agent();
    return directAgent;
  }
  if (m === "on") {
    const proxy = getActiveProxy();
    if (!proxy) return undefined;
    let agent = proxyAgents.get(proxy);
    if (!agent) {
      agent = new ProxyAgent(proxy);
      proxyAgents.set(proxy, agent);
    }
    return agent;
  }
  return undefined;
}

export function buildSourceFetchInit(
  cfg: {
    cookie?: string;
    userAgent?: string;
    proxyMode?: ProxyMode;
    timeoutMs?: number;
  },
  opts?: {
    method?: string;
    referer?: string;
    timeoutMs?: number;
    accept?: string;
  },
): RequestInit {
  const headers: Record<string, string> = {
    "User-Agent": (cfg.userAgent || "").trim() || DEFAULT_UA,
    Accept: opts?.accept || "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
  };
  if (opts?.referer) headers.Referer = opts.referer;
  const cookie = (cfg.cookie || "").trim();
  if (cookie) headers.Cookie = cookie;
  const timeout =
    opts?.timeoutMs ||
    (cfg.timeoutMs && cfg.timeoutMs > 0
      ? cfg.timeoutMs
      : Number(process.env.SCRAPE_TIMEOUT_MS || 8000));
  const init: RequestInit = {
    method: opts?.method || "GET",
    headers,
    redirect: "follow",
    signal: AbortSignal.timeout(timeout),
  };
  const dispatcher = dispatcherFor(cfg.proxyMode);
  if (dispatcher) init.dispatcher = dispatcher;
  return init;
}

/** 供 fetchText / 封面下载合并 ALS 画像 */
export function resolveFetchOptions(opts?: {
  referer?: string;
  timeoutMs?: number;
  cookie?: string;
  userAgent?: string;
  proxyMode?: ProxyMode;
}): {
  headers: Record<string, string>;
  timeoutMs: number;
  retry: number;
  dispatcher?: Dispatcher;
} {
  const profile = getRequestProfile();
  const userAgent =
    (opts?.userAgent || profile.userAgent || "").trim() || DEFAULT_UA;
  const cookie = (opts?.cookie || profile.cookie || "").trim();
  const headers: Record<string, string> = {
    "User-Agent": userAgent,
    Accept: "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
  };
  if (opts?.referer) headers.Referer = opts.referer;
  if (cookie) headers.Cookie = cookie;
  const timeoutMs =
    opts?.timeoutMs ||
    profile.timeoutMs ||
    Number(process.env.SCRAPE_TIMEOUT_MS || 8000);
  const retry = Math.max(0, Math.min(5, profile.retry ?? 1));
  const dispatcher = dispatcherFor(opts?.proxyMode || profile.proxyMode);
  return { headers, timeoutMs, retry, dispatcher };
}

export { DEFAULT_UA };

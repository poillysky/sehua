import { Agent, ProxyAgent, setGlobalDispatcher } from "undici";

let activeProxy = "";

export function getActiveProxy(): string {
  return activeProxy;
}

/** 立即切换全局 fetch 代理；空字符串=直连 */
export function applyProxy(url: string | null | undefined): void {
  const trimmed = String(url || "").trim();
  if (!trimmed) {
    setGlobalDispatcher(new Agent());
    activeProxy = "";
    console.log("[scrape-web] proxy cleared (direct)");
    return;
  }
  setGlobalDispatcher(new ProxyAgent(trimmed));
  activeProxy = trimmed;
  console.log(`[scrape-web] using proxy ${trimmed}`);
}

/** @deprecated 用 applyProxy；保留兼容旧调用 */
export function applyProxyFromEnv(): void {
  const proxy =
    process.env.HTTPS_PROXY ||
    process.env.HTTP_PROXY ||
    process.env.ALL_PROXY ||
    process.env.https_proxy ||
    process.env.http_proxy ||
    "";
  applyProxy(proxy);
}

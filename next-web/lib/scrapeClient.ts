/** 服务端转发到 scrape-web（浏览器不直连 :9209） */

export function scrapeOrigin(): string {
  return (
    process.env.SCRAPE_ORIGIN ||
    process.env.COVER_ORIGIN ||
    "http://127.0.0.1:9209"
  ).replace(/\/$/, "");
}

export async function scrapeFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const url = `${scrapeOrigin()}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init?.headers || {});
  const token = (process.env.SCRAPE_API_TOKEN || "").trim();
  if (token && !headers.has("authorization")) {
    headers.set("authorization", `Bearer ${token}`);
  }
  return fetch(url, {
    ...init,
    headers,
    cache: "no-store",
  });
}

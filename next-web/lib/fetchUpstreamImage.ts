import http from "node:http";
import https from "node:https";

import { expandForumCdnUrls } from "@/lib/imageProxy";

const UPSTREAM_TIMEOUT_MS = Number(process.env.IMAGE_PROXY_TIMEOUT_MS || 12_000);

const DEFAULT_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  Accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
};

function headersForUrl(url: string): Record<string, string> {
  const host = new URL(url).hostname.toLowerCase();
  if (host === "pics.dmm.co.jp" || host.endsWith(".dmm.co.jp")) {
    return {
      ...DEFAULT_HEADERS,
      Referer: "https://www.dmm.co.jp/",
    };
  }
  return {
    ...DEFAULT_HEADERS,
    Referer: "https://www.sehuatang.net/",
  };
}

function fetchOneUpstreamImage(
  url: string,
): Promise<{ buffer: Buffer; contentType: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const lib = parsed.protocol === "https:" ? https : http;

    const req = lib.get(
      url,
      {
        headers: headersForUrl(url),
        timeout: UPSTREAM_TIMEOUT_MS,
        family: 4,
      },
      (res) => {
        if (
          res.statusCode &&
          res.statusCode >= 300 &&
          res.statusCode < 400 &&
          res.headers.location
        ) {
          const nextUrl = new URL(res.headers.location, url).toString();
          fetchOneUpstreamImage(nextUrl).then(resolve).catch(reject);
          return;
        }

        if (!res.statusCode || res.statusCode >= 400) {
          reject(new Error(`Upstream error: ${res.statusCode}`));
          return;
        }

        const chunks: Buffer[] = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () =>
          resolve({
            buffer: Buffer.concat(chunks),
            contentType: res.headers["content-type"] || "image/jpeg",
          }),
        );
        res.on("error", reject);
      },
    );

    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Upstream timeout"));
    });
  });
}

/** 拉图；论坛 tu.* 图床 404 时自动换镜像主机 */
export async function fetchUpstreamImage(
  url: string,
): Promise<{ buffer: Buffer; contentType: string }> {
  const candidates = expandForumCdnUrls(url);
  let lastError: unknown;
  for (const cand of candidates) {
    try {
      return await fetchOneUpstreamImage(cand);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Image upstream failed");
}

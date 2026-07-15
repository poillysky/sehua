import dns from "node:dns";
import http from "node:http";
import https from "node:https";

const UPSTREAM_TIMEOUT_MS = Number(process.env.IMAGE_PROXY_TIMEOUT_MS || 30_000);

const UPSTREAM_HEADERS = {
  Referer: "https://www.sehuatang.net/",
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  Accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
};

function ipv4Lookup(
  hostname: string,
  _options: unknown,
  callback: (
    err: NodeJS.ErrnoException | null,
    address: string,
    family?: number,
  ) => void,
) {
  dns.lookup(hostname, { family: 4 }, callback);
}

export function fetchUpstreamImage(
  url: string,
): Promise<{ buffer: Buffer; contentType: string }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const lib = parsed.protocol === "https:" ? https : http;

    const req = lib.get(
      url,
      {
        headers: UPSTREAM_HEADERS,
        lookup: ipv4Lookup,
        timeout: UPSTREAM_TIMEOUT_MS,
      },
      (res) => {
        if (
          res.statusCode &&
          res.statusCode >= 300 &&
          res.statusCode < 400 &&
          res.headers.location
        ) {
          const nextUrl = new URL(res.headers.location, url).toString();
          fetchUpstreamImage(nextUrl).then(resolve).catch(reject);
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

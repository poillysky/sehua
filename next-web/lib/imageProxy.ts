const DEFAULT_ALLOWED_IMAGE_HOSTS = [
  "tu.ewrewej.la",
  "www.sehuatang.net",
  "sehuatang.net",
  "www.sehuatang.org",
  "sehuatang.org",
];

function getAllowedImageHosts() {
  const extra = process.env.IMAGE_PROXY_ALLOWED_HOSTS?.split(",")
    .map((host) => host.trim())
    .filter(Boolean);

  return new Set([...DEFAULT_ALLOWED_IMAGE_HOSTS, ...(extra || [])]);
}

function matchesAllowedHost(hostname: string, allowedHosts: Set<string>) {
  for (const host of Array.from(allowedHosts)) {
    if (hostname === host || hostname.endsWith(`.${host}`)) {
      return true;
    }
  }

  return false;
}

export function isAllowedImageUrl(url: string) {
  try {
    const parsed = new URL(url);

    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      return false;
    }

    return matchesAllowedHost(parsed.hostname, getAllowedImageHosts());
  } catch {
    return false;
  }
}

export function buildImageProxyUrl(url: string) {
  return `/api/image-proxy?url=${encodeURIComponent(url)}`;
}

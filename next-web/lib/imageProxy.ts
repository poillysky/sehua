const DEFAULT_ALLOWED_IMAGE_HOSTS = [
  "tu.ewrewej.la",
  "tu.ymawv.la",
  "tu.ldkms.la",
  "www.sehuatang.net",
  "sehuatang.net",
  "www.sehuatang.org",
  "sehuatang.org",
  "picdcd.com",
  "adipcd.com",
  "pkapic.cc",
  "www.imgccc.com",
  "imgccc.com",
  "i.11img.com",
  "qpic.ws",
  "gdvdvb.com",
  "pic.img906.com",
  "img.yichkp.com",
  "tuj.microsoftsa.com",
  "cloud95.xunse.pics",
  "pics.dmm.co.jp",
  "dmm.co.jp",
  "imagetwist.com",
  "gifyu.com",
  "contents.fc2.com",
  "fc2.com",
  "mgstage.com",
  "1pondo.tv",
  "10musume.com",
  "caribbeancom.com",
  "pacopacomama.com",
  "023pic3.cc",
  "pic26077.cc",
  "pic2607a.cc",
  "pic505hz.cc",
  "pid505st.cc",
];

/** Discuz 图床镜像：同路径在某一台上 404 时换主机常仍可取（如 tid=3657635） */
export const FORUM_TU_CDN_HOSTS = [
  "tu.ewrewej.la",
  "tu.ymawv.la",
  "tu.ldkms.la",
] as const;

const FORUM_TU_CDN_HOST_RE = /^tu\.(?:ewrewej|ymawv|ldkms)\.la$/i;

/**
 * 色花堂 tu.* 图床：保留原 URL，再追加其它镜像主机（同 path）。
 * 非该类 URL 原样返回单元素数组。
 */
export function expandForumCdnUrls(url: string): string[] {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    if (!FORUM_TU_CDN_HOST_RE.test(host)) return [url];
    if (!parsed.pathname.includes("/tupian/forum/")) return [url];
    const out: string[] = [url];
    const seen = new Set([host]);
    for (const alt of FORUM_TU_CDN_HOSTS) {
      if (seen.has(alt)) continue;
      seen.add(alt);
      const next = new URL(url);
      next.hostname = alt;
      out.push(next.toString());
    }
    return out;
  } catch {
    return [url];
  }
}
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

function isPrivateHostname(hostname: string) {
  const h = hostname.toLowerCase();
  if (h === "localhost" || h === "127.0.0.1" || h === "::1" || h === "0.0.0.0") {
    return true;
  }
  if (/^(10\.|192\.168\.|169\.254\.)/.test(h)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(h)) return true;
  return false;
}

/** 白名单命中，或公网 URL 且路径像图片 */
export function isAllowedImageUrl(url: string) {
  try {
    const parsed = new URL(url);

    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      return false;
    }

    const host = parsed.hostname.toLowerCase();
    if (isPrivateHostname(host)) return false;

    if (matchesAllowedHost(host, getAllowedImageHosts())) {
      return true;
    }

    return /\.(jpe?g|png|gif|webp|avif|bmp)(\?|#|$)/i.test(parsed.pathname);
  } catch {
    return false;
  }
}

export function buildImageProxyUrl(url: string) {
  return `/api/image-proxy?url=${encodeURIComponent(url)}`;
}

/** 本机 Node 常连不上的图床，选封面时降权 */
export function isUnreliableCoverHost(url: string) {
  return /dmm\.co\.jp|imagetwist\.com|gifyu\.com/i.test(url);
}

/**
 * 色花堂帖内图床（论坛 CDN / 附件图），选封面时最优先。
 * 不含 DMM、片商官网、imagetwist 等外链。
 */
export function isForumCoverHost(url: string) {
  return /sehuatang\.(net|org)|picdcd\.com|adipcd\.com|pkapic\.cc|imgccc\.com|11img\.com|yichkp\.com|ewrewej\.la|ymawv\.la|ldkms\.la|qpic\.ws|gdvdvb\.com|img906\.com|microsoftsa\.com|xunse\.pics|023pic3\.cc|pic26077\.cc|pic2607a\.cc|pic505hz\.cc|pid505st\.cc/i.test(
    url,
  );
}

/** 封面排序分：本地刮削封面 > 色花堂图床 > 其他可代理图 > 不稳定外链 */
export function coverHostPriority(url: string | null | undefined): number {
  if (!url) return 0;
  if (url.startsWith("/covers/")) return 5;
  if (isUnreliableCoverHost(url)) return 1;
  if (isForumCoverHost(url)) return 3;
  return 2;
}

/** URL 形态暗示横图（FC2 封面优选） */
export function landscapeUrlHint(url: string): number {
  const u = url.toLowerCase();
  if (/[_\-](?:l|ll|xl|wide|landscape|banner|cover_l|pl)\.(jpe?g|png|webp)/i.test(u)) {
    return 2;
  }
  if (/\/(?:l|ll|wide|landscape|banner)\//i.test(u)) {
    return 2;
  }
  if (/[_\-](?:s|ss|ps|portrait|cover_s)\.(jpe?g|png|webp)/i.test(u)) {
    return -2;
  }
  if (/contents\.fc2\.com/i.test(u)) {
    return 1;
  }
  return 0;
}

/** 刮削封面路径：/covers/xxx.jpg → 浏览器可访问的 URL */

export function isLocalCoverPath(url: string | null | undefined): boolean {
  if (!url) return false;
  return url.startsWith("/covers/");
}

/**
 * next-web 与 scrape-web 分端口时，把相对 /covers 指到刮削服务。
 * 生产可用 next rewrite 同域反代，此时 COVER_PUBLIC_ORIGIN 可留空。
 */
export function resolveCoverUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (!isLocalCoverPath(url)) return url;
  const origin = (
    process.env.COVER_PUBLIC_ORIGIN ||
    process.env.NEXT_PUBLIC_COVER_ORIGIN ||
    ""
  ).replace(/\/$/, "");
  if (!origin) return url;
  return `${origin}${url}`;
}

"use client";

import { useMemo, useState, type CSSProperties } from "react";

import { resolveCoverUrl, isLocalCoverPath } from "@/lib/coverUrl";
import {
  buildImageProxyUrl,
  coverHostPriority,
  expandForumCdnUrls,
  isForumCoverHost,
  isUnreliableCoverHost,
  landscapeUrlHint,
} from "@/lib/imageProxy";

type PreviewImageProps = {
  src?: string | null;
  /** 多候选：优先展示能加载成功的（按数组顺序） */
  srcs?: string[];
  alt: string;
  className?: string;
  style?: CSSProperties;
  loading?: "lazy" | "eager";
  fetchPriority?: "high" | "low" | "auto";
  preferProxy?: boolean;
  /** 多候选时优先宽>高的横图（FC2 等） */
  preferLandscape?: boolean;
  /** 最多尝试几条源 URL（默认 6：含图床镜像） */
  maxSources?: number;
  /** 全部候选加载失败（含 404）时回调；组件自身不再渲染占位 */
  onAllFailed?: () => void;
};

function buildAttemptUrls(
  candidates: string[],
  preferProxy: boolean,
): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const push = (u: string) => {
    if (!u || seen.has(u)) return;
    seen.add(u);
    out.push(u);
  };

  for (const raw of candidates) {
    if (isLocalCoverPath(raw)) {
      const resolved = resolveCoverUrl(raw) || raw;
      push(resolved);
      continue;
    }
    // 论坛 tu.* 图床：原主机优先，失败再换镜像
    for (const variant of expandForumCdnUrls(raw)) {
      const direct = resolveCoverUrl(variant) || variant;
      const proxied = isUnreliableCoverHost(variant)
        ? null
        : buildImageProxyUrl(variant);
      const preferDirect =
        !preferProxy ||
        isForumCoverHost(variant) ||
        isUnreliableCoverHost(variant);
      if (preferDirect) {
        push(direct);
        if (proxied) push(proxied);
      } else {
        if (proxied) push(proxied);
        push(direct);
      }
    }
  }
  return out;
}

export function PreviewImage({
  src,
  srcs,
  alt,
  className,
  style,
  loading = "lazy",
  fetchPriority,
  preferProxy = false,
  preferLandscape = false,
  maxSources = 6,
  onAllFailed,
}: PreviewImageProps) {
  const attempts = useMemo(() => {
    const candidates = (
      srcs && srcs.length > 0 ? srcs.filter(Boolean) : src ? [src] : []
    )
      .sort((a, b) => {
        const byHost = coverHostPriority(b) - coverHostPriority(a);
        if (byHost) return byHost;
        if (preferLandscape) return landscapeUrlHint(b) - landscapeUrlHint(a);
        return 0;
      })
      .slice(0, Math.max(1, maxSources));
    return buildAttemptUrls(candidates, preferProxy);
  }, [src, srcs, preferProxy, preferLandscape, maxSources]);

  const attemptsKey = attempts.join("|");
  const [index, setIndex] = useState(0);
  const [failedKey, setFailedKey] = useState("");

  // 候选变化时重置（用 key 同步，避免 effect 空窗）
  const activeIndex = failedKey === attemptsKey ? index : 0;
  const exhausted = activeIndex >= attempts.length;
  const imgSrc = exhausted ? "" : attempts[activeIndex] || "";

  if (!attempts.length || exhausted || !imgSrc) {
    return null;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt={alt}
      className={className}
      decoding="async"
      fetchPriority={fetchPriority}
      loading={loading}
      referrerPolicy="strict-origin-when-cross-origin"
      src={imgSrc}
      style={style}
      onError={() => {
        const next = (failedKey === attemptsKey ? index : 0) + 1;
        if (next < attempts.length) {
          setFailedKey(attemptsKey);
          setIndex(next);
          return;
        }
        setFailedKey(attemptsKey);
        setIndex(attempts.length);
        onAllFailed?.();
      }}
    />
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import clsx from "clsx";

import { PreviewImage } from "@/components/PreviewImage";
import {
  codeSearchHref,
  isFc2Code,
  isFullCoverCode,
} from "@/utils/av-code";

/** 日本分区番号链：带 jp=1，搜索页才套用中文/破解偏好 */
export function JapanCodeSearchLink({
  code,
  coverUrl,
  coverUrls,
  className,
  loading = "lazy",
  fetchPriority,
  landscapeCover,
}: {
  code: string;
  coverUrl?: string | null;
  coverUrls?: string[];
  className?: string;
  loading?: "lazy" | "eager";
  fetchPriority?: "high" | "low" | "auto";
  /** 强制横图（无码厂牌列表） */
  landscapeCover?: boolean;
}) {
  const [href, setHref] = useState(() => codeSearchHref(code));
  const candidates =
    coverUrls && coverUrls.length > 0
      ? coverUrls
      : coverUrl
        ? [coverUrl]
        : [];
  const fullCover =
    landscapeCover || isFc2Code(code) || isFullCoverCode(code);

  useEffect(() => {
    setHref(codeSearchHref(code, { japanPrefs: true }));
  }, [code]);

  return (
    <Link className={className} href={href}>
      <span
        className={clsx(
          "relative block w-full overflow-hidden bg-default-100 dark:bg-slate-800",
          fullCover ? "aspect-[16/10]" : "aspect-[2/3]",
        )}
      >
        <PreviewImage
          alt={code}
          className={clsx(
            "h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]",
            fullCover
              ? "object-center origin-center"
              : "object-right-top origin-right",
          )}
          loading={loading}
          fetchPriority={fetchPriority}
          maxSources={2}
          preferLandscape={fullCover}
          srcs={candidates.slice(0, 2)}
          style={fullCover ? undefined : { objectPosition: "right top" }}
        />
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/25 to-transparent opacity-0 transition-opacity group-hover:opacity-100"
        />
      </span>
      <span className="block break-all px-1 py-1.5 text-center text-[11px] font-semibold leading-snug tracking-wide text-foreground transition-colors group-hover:text-primary sm:px-2 sm:py-2 sm:text-sm">
        {code}
      </span>
    </Link>
  );
}

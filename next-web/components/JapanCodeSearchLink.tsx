"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import clsx from "clsx";

import {
  coverDisplayFromAspect,
  resolveCoverDisplay,
  type CoverAspect,
} from "@/config/av-makers";
import { PreviewImage } from "@/components/PreviewImage";
import { codeSearchHref, isFc2Code, isFullCoverCode } from "@/utils/av-code";

function displayForCode(code: string, coverAspect?: CoverAspect) {
  if (coverAspect) return coverDisplayFromAspect(coverAspect);
  const prefixGuess = String(code || "")
    .trim()
    .toUpperCase()
    .split(/[-_\s]/)[0];
  if (isFc2Code(code)) return resolveCoverDisplay("FC2");
  if (isFullCoverCode(code)) {
    const d = resolveCoverDisplay(prefixGuess || code);
    return d.preferLandscape ? d : coverDisplayFromAspect("16/9");
  }
  return resolveCoverDisplay(prefixGuess || code);
}

/** 日本分区番号链：带 jp=1，搜索页才套用中文/破解偏好 */
export function JapanCodeSearchLink({
  code,
  coverUrl,
  coverUrls,
  className,
  loading = "lazy",
  fetchPriority,
  coverAspect,
}: {
  code: string;
  coverUrl?: string | null;
  coverUrls?: string[];
  className?: string;
  loading?: "lazy" | "eager";
  fetchPriority?: "high" | "low" | "auto";
  /** 板块级封面比例（如 `16/9`）；列表页按前缀传入 */
  coverAspect?: CoverAspect;
}) {
  const [href, setHref] = useState(() => codeSearchHref(code));
  const candidates =
    coverUrls && coverUrls.length > 0
      ? coverUrls
      : coverUrl
        ? [coverUrl]
        : [];
  const display = displayForCode(code, coverAspect);

  useEffect(() => {
    setHref(codeSearchHref(code, { japanPrefs: true }));
  }, [code]);

  return (
    <Link className={className} href={href}>
      <span
        className="relative block w-full overflow-hidden bg-default-100 dark:bg-slate-800"
        style={{ aspectRatio: display.aspectRatio }}
      >
        <PreviewImage
          alt={code}
          className={clsx(
            "h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]",
            display.preferLandscape
              ? "object-center origin-center"
              : "object-right-top origin-right",
          )}
          loading={loading}
          fetchPriority={fetchPriority}
          maxSources={2}
          preferLandscape={display.preferLandscape}
          srcs={candidates.slice(0, 2)}
          style={
            display.preferLandscape
              ? undefined
              : { objectPosition: display.objectPosition }
          }
        />
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/25 to-transparent opacity-0 transition-opacity group-hover:opacity-100"
        />
      </span>
      <span className="block whitespace-nowrap px-1 py-1.5 text-center text-[9px] font-semibold leading-snug tracking-wide text-foreground transition-colors group-hover:text-primary sm:px-1.5 sm:py-2 sm:text-[11px]">
        {code}
      </span>
    </Link>
  );
}

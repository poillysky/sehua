"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import clsx from "clsx";

import { ChevronRightIcon } from "@/components/BrowseIcons";
import { PreviewImage } from "@/components/PreviewImage";
import { codeSearchHref, isFc2Code } from "@/utils/av-code";

/** 日本分区番号链：带 jp=1，搜索页才套用中文/破解偏好 */
export function JapanCodeSearchLink({
  code,
  coverUrl,
  coverUrls,
  className,
}: {
  code: string;
  coverUrl?: string | null;
  coverUrls?: string[];
  className?: string;
}) {
  const [href, setHref] = useState(() => codeSearchHref(code));
  const candidates =
    coverUrls && coverUrls.length > 0
      ? coverUrls
      : coverUrl
        ? [coverUrl]
        : [];
  const fc2 = isFc2Code(code);

  useEffect(() => {
    setHref(codeSearchHref(code, { japanPrefs: true }));
  }, [code]);

  return (
    <Link className={className} href={href}>
      <span className="flex min-w-0 items-center gap-3">
        <span
          className={clsx(
            "relative shrink-0 overflow-hidden rounded-md bg-default-100 dark:bg-slate-800",
            fc2 ? "h-10 w-[4.5rem]" : "h-14 w-10",
          )}
        >
          <PreviewImage
            alt={code}
            className={clsx(
              "h-full w-full object-cover",
              fc2 ? "object-center" : "object-right",
            )}
            loading="lazy"
            preferLandscape={fc2}
            preferProxy
            srcs={candidates}
          />
        </span>
        <span className="truncate text-sm font-semibold tracking-wide text-foreground group-hover:text-primary">
          {code}
        </span>
      </span>
      <ChevronRightIcon
        className="shrink-0 text-default-300 transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
        size={16}
      />
    </Link>
  );
}

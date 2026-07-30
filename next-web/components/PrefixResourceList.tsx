"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

import type { PrefixResourceHit } from "@/app/api/graphql/service";
import { JapanCodeSearchLink } from "@/components/JapanCodeSearchLink";
import { HIDE_GLOBAL_BACK_ATTR } from "@/components/PageBackButton";
import { findMakerByPrefix, resolveCoverDisplay } from "@/config/av-makers";

/**
 * 前缀/女优封面格 + 翻页。
 * 手机：上滚封面、底栏固定翻页（封面区下方，不盖图、不被 Safari 藏住）。
 * 桌面：封面后普通文档流翻页。
 */
export function PrefixResourceList({
  prefix,
  items,
  totalCount,
  page,
  pageSize,
  labels,
  buildPageHref,
  subtitle,
}: {
  prefix: string;
  items: PrefixResourceHit[];
  totalCount: number;
  page: number;
  pageSize: number;
  labels: {
    empty: string;
    prev: string;
    next: string;
    pageOf?: string;
  };
  buildPageHref?: (page: number) => string;
  subtitle?: string;
}) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const hrefFor = buildPageHref || ((p: number) => (p <= 1 ? "?" : `?p=${p}`));
  const showPager = totalCount > pageSize;
  const hasPrev = page > 1;
  const hasNext = page < totalPages;
  const pageLabel = labels.pageOf || `${page} / ${totalPages}`;
  const prevHref = hrefFor(page - 1);
  const nextHref = hrefFor(page + 1);
  const listScrollRef = useRef<HTMLDivElement>(null);
  /** 已知厂牌前缀才锁板块比例；女优页等按番号自行推断 */
  const coverAspect = findMakerByPrefix(prefix)
    ? resolveCoverDisplay(prefix).aspect
    : undefined;

  useEffect(() => {
    if (!showPager) return;
    document.documentElement.setAttribute(HIDE_GLOBAL_BACK_ATTR, "1");
    return () => {
      document.documentElement.removeAttribute(HIDE_GLOBAL_BACK_ATTR);
    };
  }, [showPager]);

  // 翻页后回到列表顶部（手机滚封面容器，桌面滚窗口）
  useEffect(() => {
    listScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [page, prefix]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 max-md:overflow-hidden md:gap-4 md:overflow-visible">
      <div className="flex shrink-0 flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-xl font-semibold tracking-tight text-foreground md:text-2xl">
          {prefix}
        </h1>
        {subtitle ? (
          <span className="text-sm text-default-500 dark:text-slate-400">
            {subtitle}
          </span>
        ) : null}
      </div>

      {/* 手机：仅封面区滚动；翻页在下方固定槽位 */}
      <div
        ref={listScrollRef}
        className="min-h-0 max-md:flex-1 max-md:overflow-y-auto max-md:overscroll-y-contain max-md:[-webkit-overflow-scrolling:touch] md:overflow-visible"
      >
        {items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-default-300/80 px-4 py-12 text-center text-sm text-default-500 dark:border-slate-600">
            {labels.empty}
          </div>
        ) : (
          <div className="relative z-0 grid grid-cols-3 gap-2 pb-2 sm:gap-2.5 md:grid-cols-4 md:gap-3">
            {items.map(({ code, coverUrl, coverUrls }, index) => (
              <JapanCodeSearchLink
                key={code}
                className="group relative z-0 flex flex-col overflow-hidden rounded-2xl border border-default-200/60 bg-white/90 shadow-soft backdrop-blur-md transition-[border-color,box-shadow,background-color] duration-200 hover:border-primary/40 hover:shadow-card dark:border-slate-600/50 dark:bg-slate-800/80 dark:hover:border-primary/35"
                code={code}
                coverUrl={coverUrl}
                coverUrls={coverUrls}
                coverAspect={coverAspect}
                fetchPriority={index < 6 ? "high" : "auto"}
                loading={index < 8 ? "eager" : "lazy"}
              />
            ))}
          </div>
        )}
      </div>

      {showPager ? (
        <nav
          aria-label="pagination"
          className="prefix-pager flex w-full shrink-0 items-center gap-2 border-t border-default-200 bg-background px-1 pt-3 dark:border-slate-700 md:mt-6 md:pb-2"
          style={{
            paddingBottom: "max(0.75rem, env(safe-area-inset-bottom, 0px))",
          }}
        >
          {hasPrev ? (
            <Link
              className="inline-flex min-h-11 min-w-[4.5rem] flex-1 items-center justify-center rounded-xl border border-default-300 bg-content1 text-sm font-medium text-default-700 active:opacity-80 dark:border-slate-600 dark:text-slate-200"
              href={prevHref}
              prefetch={false}
              scroll
            >
              {labels.prev}
            </Link>
          ) : (
            <span className="inline-flex min-h-11 min-w-[4.5rem] flex-1 items-center justify-center rounded-xl border border-default-200 text-sm text-default-300 dark:border-slate-700 dark:text-slate-600">
              {labels.prev}
            </span>
          )}
          <span className="shrink-0 px-1 text-center text-sm tabular-nums text-default-500">
            {pageLabel}
          </span>
          {hasNext ? (
            <Link
              className="inline-flex min-h-11 min-w-[4.5rem] flex-1 items-center justify-center rounded-xl bg-primary text-sm font-semibold text-primary-foreground active:opacity-90"
              href={nextHref}
              prefetch={false}
              scroll
            >
              {labels.next}
            </Link>
          ) : (
            <span className="inline-flex min-h-11 min-w-[4.5rem] flex-1 items-center justify-center rounded-xl border border-default-200 text-sm text-default-300 dark:border-slate-700 dark:text-slate-600">
              {labels.next}
            </span>
          )}
        </nav>
      ) : null}
    </div>
  );
}

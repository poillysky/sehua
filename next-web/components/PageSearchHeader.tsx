"use client";

import { Suspense, useEffect, useRef, type ReactNode } from "react";
import clsx from "clsx";

import { BrowsePrefToggles } from "@/components/BrowsePrefToggles";
import {
  ForumBreadcrumb,
  type ForumCrumb,
} from "@/components/ForumBreadcrumb";
import { SearchInput } from "@/components/SearchInput";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import type { SearchKind } from "@/hooks/useSearchPreferences";

function SearchFallback() {
  return (
    <div
      aria-hidden
      className="h-11 min-w-0 flex-1 rounded-full bg-white/70 ring-1 ring-default-200/50 sm:h-12 dark:bg-slate-800/50 dark:ring-slate-600/40"
    />
  );
}

/**
 * 非浏览页吸顶栏（搜索 / 详情 / 女优）。
 * 浏览分区请用 ForumShell（自带搜索+面包屑），勿与本组件叠用。
 */
export function PageSearchHeader({
  japanPrefs = false,
  crumbs,
  defaultValue,
  defaultSearchKind,
  compact = false,
  className,
  endSlot,
}: {
  japanPrefs?: boolean;
  /** 搜索/女优等：传 crumbs 显示第二行；浏览页不要用本组件 */
  crumbs?: ForumCrumb[];
  defaultValue?: string;
  defaultSearchKind?: SearchKind;
  /** 手机壳内：略减边距，且 top=0（safe-area 由 prefix-mobile-shell 承担） */
  compact?: boolean;
  className?: string;
  endSlot?: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const showCrumbs = Boolean(crumbs?.length);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;

    const sync = () => {
      document.documentElement.style.setProperty(
        "--page-search-h",
        `${Math.ceil(el.getBoundingClientRect().height)}px`,
      );
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => {
      ro.disconnect();
      document.documentElement.style.removeProperty("--page-search-h");
    };
  }, [showCrumbs, crumbs?.length]);

  return (
    <div
      ref={rootRef}
      className={clsx(
        "page-search-sticky sticky z-30",
        compact
          ? "top-0"
          : "top-[max(0px,var(--safe-top))]",
        "bg-white shadow-[0_1px_0_rgba(15,23,42,0.06)]",
        "dark:bg-slate-900 dark:shadow-[0_1px_0_rgba(255,255,255,0.08)]",
        className,
      )}
    >
      <div
        className={clsx(
          "mx-auto flex w-full min-w-0 max-w-6xl items-center gap-1 overflow-x-clip px-3 md:px-4 lg:max-w-7xl",
          compact ? "py-2 md:pt-3 md:pb-2" : "pt-3 pb-2",
        )}
      >
        <SiteLogoLink />
        <Suspense fallback={<SearchFallback />}>
          <SearchInput
            defaultSearchKind={defaultSearchKind}
            defaultValue={defaultValue}
            japanPrefs={japanPrefs}
          />
        </Suspense>
        {endSlot ?? <SettingsNavLink />}
      </div>

      {showCrumbs ? (
        <div className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-1.5 px-3 pb-2.5 pt-1.5 shadow-[inset_0_1px_0_rgba(15,23,42,0.06)] md:px-4 lg:max-w-7xl dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
          <div className="flex min-w-0 items-center justify-between gap-2">
            <ForumBreadcrumb items={crumbs || []} />
            {japanPrefs ? <BrowsePrefToggles /> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

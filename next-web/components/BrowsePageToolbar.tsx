"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { BrowseRefreshButton } from "@/components/BrowseRefreshButton";
import { ShuffleIcon } from "@/components/BrowseIcons";

export function BrowsePageToolbar({
  loading = false,
  totalCount,
  boardLabel,
  backHref,
  onRefresh,
}: {
  loading?: boolean;
  totalCount?: number;
  boardLabel?: string;
  /** 返回父版 / 分区；缺省回首页 */
  backHref?: string;
  onRefresh?: () => void;
}) {
  const t = useTranslations();
  const hasCount = typeof totalCount === "number" && totalCount > 0;
  const title = boardLabel || t("Browse.title");
  const parentHref = backHref || "/";

  return (
    <header className="group relative overflow-hidden rounded-2xl border border-default-200/60 bg-white/90 shadow-card backdrop-blur-md dark:border-slate-600/50 dark:bg-slate-800/80">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/8 via-transparent to-emerald-300/10"
      />

      <div className="relative flex items-center justify-between gap-4 px-4 py-4 md:px-5 md:py-5">
        <div className="flex min-w-0 items-center gap-3.5 md:gap-4">
          <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-soft md:h-12 md:w-12">
            <ShuffleIcon size={20} />
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold tracking-tight text-foreground md:text-xl">
                {title}
              </h1>
              {hasCount ? (
                <span className="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium tabular-nums text-primary">
                  {t("Browse.total_count", { count: totalCount })}
                </span>
              ) : null}
            </div>
            <p className="mt-1 truncate text-xs text-default-500 md:text-sm">
              {t("Browse.filtered_subtitle")}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Link
                className="text-xs font-medium text-primary hover:underline"
                href={parentHref}
              >
                {t("Boards.back_nav")}
              </Link>
            </div>
          </div>
        </div>

        <BrowseRefreshButton isLoading={loading} onRefresh={onRefresh} />
      </div>
    </header>
  );
}

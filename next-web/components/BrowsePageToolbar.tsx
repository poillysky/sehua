"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { BrowseRefreshButton } from "@/components/BrowseRefreshButton";
import { ShuffleIcon } from "@/components/BrowseIcons";

export function BrowsePageToolbar({
  loading = false,
  totalCount,
  boardLabel,
  onRefresh,
}: {
  loading?: boolean;
  totalCount?: number;
  boardLabel?: string;
  onRefresh?: () => void;
}) {
  const t = useTranslations();
  const hasCount = typeof totalCount === "number" && totalCount > 0;
  const filtered = Boolean(boardLabel);

  return (
    <header className="group relative overflow-hidden rounded-2xl border border-default-200/70 bg-content1 shadow-sm dark:border-slate-700/70">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-sky-400/10 dark:from-primary/15 dark:to-sky-500/5"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-6 top-1/2 h-24 w-24 -translate-y-1/2 rounded-full border border-primary/10 opacity-60 transition-transform duration-500 group-hover:scale-110 dark:border-primary/20"
      />

      <div className="relative flex items-center justify-between gap-4 px-4 py-4 md:px-5 md:py-5">
        <div className="flex min-w-0 items-center gap-3.5 md:gap-4">
          <div className="relative shrink-0">
            <div
              aria-hidden
              className="absolute inset-0 rounded-2xl bg-primary/20 blur-md"
            />
            <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary-600 text-primary-foreground shadow-md shadow-primary/25 md:h-12 md:w-12">
              <ShuffleIcon className="drop-shadow-sm" size={20} />
            </div>
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold tracking-tight text-foreground md:text-xl">
                {filtered ? boardLabel : t("Browse.title")}
              </h1>
              {hasCount ? (
                <span className="inline-flex items-center rounded-full border border-default-200/80 bg-background/70 px-2 py-0.5 text-[11px] font-medium tabular-nums text-default-600 backdrop-blur-sm dark:border-slate-600 dark:bg-slate-800/70 dark:text-slate-300">
                  {t("Browse.total_count", { count: totalCount })}
                </span>
              ) : null}
            </div>
            <p className="mt-1 truncate text-xs text-default-500 md:text-sm">
              {filtered ? t("Browse.filtered_subtitle") : t("Browse.subtitle")}
            </p>
            {filtered ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Link
                  className="text-xs text-primary hover:underline"
                  href="/boards"
                >
                  {t("Boards.back_nav")}
                </Link>
                <span className="text-default-300">·</span>
                <Link
                  className="text-xs text-default-500 hover:text-primary hover:underline"
                  href="/browse"
                >
                  {t("Browse.clear_filter")}
                </Link>
              </div>
            ) : null}
          </div>
        </div>

        <BrowseRefreshButton isLoading={loading} onRefresh={onRefresh} />
      </div>
    </header>
  );
}

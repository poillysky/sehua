import Link from "next/link";

import { codeSearchHref } from "@/utils/av-code";
import type { PrefixCodeHit } from "@/app/api/graphql/service";

export function PrefixCodeIndex({
  prefix,
  note,
  codes,
  totalCodes,
  matchedRows,
  page,
  pageSize,
  searchAllHref,
  labels,
}: {
  prefix: string;
  note?: string;
  codes: PrefixCodeHit[];
  totalCodes: number;
  matchedRows: number;
  page: number;
  pageSize: number;
  searchAllHref: string;
  labels: {
    guide: string;
    total: string;
    empty: string;
    searchAll: string;
    resources: string;
    pageOf: string;
    prev: string;
    next: string;
  };
}) {
  const totalPages = Math.max(1, Math.ceil(totalCodes / pageSize));
  const hasPrev = page > 1;
  const hasNext = page < totalPages;

  return (
    <div className="flex flex-col gap-4">
      <header className="rounded-2xl border border-default-200/70 bg-content1 px-4 py-5 dark:border-slate-700/70">
        <h1 className="text-lg font-semibold text-foreground md:text-xl">
          {prefix}
        </h1>
        {note ? (
          <p className="mt-1.5 text-[13px] leading-relaxed text-default-600 dark:text-slate-300">
            {note}
          </p>
        ) : null}
        <p className="mt-2 text-xs text-default-500 md:text-sm">
          {labels.guide}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-default-500">
          <span className="rounded-lg bg-default-100 px-2.5 py-1 dark:bg-slate-800">
            {labels.total
              .replace("{codes}", String(totalCodes))
              .replace("{rows}", String(matchedRows))}
          </span>
          <Link
            className="rounded-lg border border-default-200 px-2.5 py-1 text-primary hover:bg-primary/10 dark:border-slate-700"
            href={searchAllHref}
          >
            {labels.searchAll}
          </Link>
        </div>
      </header>

      {codes.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-default-300 px-4 py-10 text-center text-sm text-default-500 dark:border-slate-600">
          {labels.empty}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {codes.map((hit) => (
            <Link
              key={hit.code}
              className="group flex flex-col rounded-xl border border-default-200/80 bg-content1 px-3.5 py-3 transition-colors hover:border-primary/40 dark:border-slate-700/80"
              href={codeSearchHref(hit.code)}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-semibold tracking-wide text-foreground group-hover:text-primary">
                  {hit.code}
                </span>
                <span className="shrink-0 text-[11px] text-default-400">
                  {labels.resources.replace("{count}", String(hit.count))}
                </span>
              </div>
              {hit.sampleTitle ? (
                <span className="mt-1 line-clamp-2 text-xs leading-relaxed text-default-500">
                  {hit.sampleTitle}
                </span>
              ) : null}
            </Link>
          ))}
        </div>
      )}

      {totalCodes > pageSize ? (
        <div className="flex items-center justify-between gap-3 text-sm">
          <span className="text-xs text-default-500">
            {labels.pageOf
              .replace("{page}", String(page))
              .replace("{total}", String(totalPages))}
          </span>
          <div className="flex gap-2">
            {hasPrev ? (
              <Link
                className="rounded-lg border border-default-200 px-3 py-1.5 dark:border-slate-700"
                href={`?p=${page - 1}`}
              >
                {labels.prev}
              </Link>
            ) : null}
            {hasNext ? (
              <Link
                className="rounded-lg border border-default-200 px-3 py-1.5 dark:border-slate-700"
                href={`?p=${page + 1}`}
              >
                {labels.next}
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

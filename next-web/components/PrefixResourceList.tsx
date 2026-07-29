import Link from "next/link";

import type { PrefixResourceHit } from "@/app/api/graphql/service";
import { JapanCodeSearchLink } from "@/components/JapanCodeSearchLink";

export function PrefixResourceList({
  prefix,
  items,
  totalCount,
  page,
  pageSize,
  labels,
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
  };
}) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const hasPrev = page > 1;
  const hasNext = page < totalPages;

  return (
    <div className="flex flex-col gap-3.5 md:gap-4">
      <h1 className="text-xl font-semibold tracking-tight text-foreground md:text-2xl">
        {prefix}
      </h1>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-default-300/80 px-4 py-12 text-center text-sm text-default-500 dark:border-slate-600">
          {labels.empty}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.map(({ code, coverUrl, coverUrls }) => (
            <JapanCodeSearchLink
              key={code}
              className="group flex items-center justify-between gap-2 rounded-xl border border-default-200/70 bg-content1 px-3 py-2.5 transition-colors hover:border-primary/40 hover:bg-primary/[0.03] dark:border-slate-700/70 dark:bg-slate-900/40"
              code={code}
              coverUrl={coverUrl}
              coverUrls={coverUrls}
            />
          ))}
        </div>
      )}

      {totalCount > pageSize ? (
        <div className="flex items-center justify-end gap-2 text-sm">
          {hasPrev ? (
            <Link
              className="rounded-xl border border-default-200 px-3 py-1.5 text-xs transition-colors hover:border-primary/35 hover:text-primary dark:border-slate-700"
              href={`?p=${page - 1}`}
            >
              {labels.prev}
            </Link>
          ) : null}
          {hasNext ? (
            <Link
              className="rounded-xl border border-default-200 px-3 py-1.5 text-xs transition-colors hover:border-primary/35 hover:text-primary dark:border-slate-700"
              href={`?p=${page + 1}`}
            >
              {labels.next}
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

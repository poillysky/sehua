import { Skeleton } from "@nextui-org/react";

import { resolveCoverDisplay } from "@/config/av-makers";

/** 番号前缀网格骨架（与 PrefixResourceList 布局对齐） */
export function PrefixResourceListSkeleton({
  prefix,
  count = 12,
}: {
  prefix?: string;
  count?: number;
}) {
  const aspectRatio = resolveCoverDisplay(prefix || "").aspectRatio;
  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-3.5 md:gap-4"
      aria-busy
      aria-hidden
    >
      {prefix ? (
        <h1 className="text-xl font-semibold tracking-tight text-foreground md:text-2xl">
          {prefix}
        </h1>
      ) : (
        <Skeleton className="h-8 w-28 rounded-md" />
      )}
      <div className="grid grid-cols-3 gap-2 sm:gap-2.5 md:grid-cols-4 md:gap-3">
        {Array.from({ length: count }).map((_, i) => (
          <div
            key={i}
            className="overflow-hidden rounded-xl border border-default-200/70 bg-content1 dark:border-slate-700/70 dark:bg-slate-900/40"
          >
            <Skeleton
              className="w-full rounded-none"
              style={{ aspectRatio }}
            />
            <div className="px-2 py-2">
              <Skeleton className="mx-auto h-4 w-4/5 rounded-md" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

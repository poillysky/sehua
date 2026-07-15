import { Skeleton } from "@nextui-org/react";

const shell =
  "overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900";
const band = "bg-gray-50 dark:bg-slate-800";

export function BrowseResourceListSkeleton() {
  return (
    <div className="flex flex-col gap-3.5 md:gap-4" aria-hidden>
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className={shell}>
          <div className={`${band} px-3 py-2.5 md:px-4`}>
            <Skeleton className="h-5 w-4/5 rounded-md" />
          </div>
          <div className="flex gap-3 px-3 py-3 md:gap-4 md:px-4">
            <Skeleton className="h-24 w-24 shrink-0 rounded-md md:h-28 md:w-28" />
            <div className="flex flex-1 flex-col gap-2 pt-1">
              <Skeleton className="h-4 w-2/5 rounded-md" />
              <Skeleton className="h-4 w-1/2 rounded-md" />
              <Skeleton className="h-4 w-1/3 rounded-md" />
            </div>
          </div>
          <div
            className={`${band} flex items-center justify-between gap-3 px-3 py-2.5 md:px-4`}
          >
            <Skeleton className="h-4 w-40 rounded-md" />
            <Skeleton className="h-8 w-28 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

import { Skeleton } from "@nextui-org/react";

import { BrowseResourceListSkeleton } from "@/components/BrowseResourceListSkeleton";

/** 搜索结果 SSR 导航时的过渡骨架 */
export default function SearchLoading() {
  return (
    <div className="w-full md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl">
      <div className="mb-7 flex items-center gap-2">
        <Skeleton className="h-9 w-9 shrink-0 rounded-full" />
        <Skeleton className="h-11 w-full rounded-2xl" />
      </div>
      <div className="my-4 grid grid-cols-2 gap-2 md:grid-cols-4" aria-busy>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-lg md:h-11" />
        ))}
      </div>
      <Skeleton className="mb-4 h-4 w-40 rounded-md" />
      <BrowseResourceListSkeleton />
    </div>
  );
}

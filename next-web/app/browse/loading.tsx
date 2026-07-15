import { BrowsePageToolbar } from "@/components/BrowsePageToolbar";
import { BrowseResourceListSkeleton } from "@/components/BrowseResourceListSkeleton";

export default function BrowseLoading() {
  return (
    <section className="mx-auto flex w-full flex-col gap-4 px-3 py-3 md:max-w-3xl md:gap-5 md:py-8 lg:max-w-4xl">
      <div className="mb-2 flex items-center gap-2 md:mb-3 md:gap-4">
        <div className="h-[50px] w-[50px] animate-pulse rounded-full bg-default-100 md:h-[60px] md:w-[60px]" />
        <div className="h-12 flex-1 animate-pulse rounded-full bg-default-100" />
      </div>
      <div className="flex flex-col gap-4 md:gap-5">
        <BrowsePageToolbar loading />
        <BrowseResourceListSkeleton />
      </div>
    </section>
  );
}

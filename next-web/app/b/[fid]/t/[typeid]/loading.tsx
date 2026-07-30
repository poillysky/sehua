import { PrefixResourceListSkeleton } from "@/components/PrefixResourceListSkeleton";

export default function SubtypeBrowseLoading() {
  return (
    <div className="mx-auto w-full max-w-6xl px-3 py-3 md:px-4 md:py-5 lg:max-w-7xl">
      <PrefixResourceListSkeleton count={12} />
    </div>
  );
}

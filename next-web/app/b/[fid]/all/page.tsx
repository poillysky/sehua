import { Metadata } from "next";
import { Suspense } from "react";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { browseResources } from "@/app/api/graphql/service";
import { BrowsePageContent } from "@/components/BrowsePageContent";
import { BrowseResourceListSkeleton } from "@/components/BrowseResourceListSkeleton";
import { BrowsePageToolbar } from "@/components/BrowsePageToolbar";
import { findByFid, legacyFidRedirect } from "@/config/boards";
import { BROWSE_PAGE_MAX, BROWSE_PAGE_SIZE } from "@/config/constant";

export const revalidate = 60;

export async function generateMetadata({
  params,
}: {
  params: { fid: string };
}): Promise<Metadata> {
  const ctx = findByFid(decodeURIComponent(params.fid));
  const t = await getTranslations();
  return {
    title: ctx
      ? `${ctx.parent.name} · ${t("Browse.title")}`
      : t("Browse.title"),
  };
}

function BrowseContentFallback() {
  return (
    <div className="flex flex-col gap-4 md:gap-5">
      <BrowsePageToolbar loading />
      <BrowseResourceListSkeleton />
    </div>
  );
}

export default async function BoardAllResourcesPage({
  params,
  searchParams,
}: {
  params: { fid: string };
  searchParams: { p?: string };
}) {
  const fid = decodeURIComponent(params.fid);
  const legacy = legacyFidRedirect(fid);
  if (legacy) redirect(legacy);
  const ctx = findByFid(fid);
  if (!ctx) notFound();

  const page = Math.min(
    Math.max(Number(searchParams.p) || 1, 1),
    BROWSE_PAGE_MAX,
  );

  const { resources, total_count } = await browseResources(null, {
    limit: BROWSE_PAGE_SIZE,
    offset: (page - 1) * BROWSE_PAGE_SIZE,
    board_parent: ctx.parent.name,
  });

  return (
    <Suspense fallback={<BrowseContentFallback />}>
      <BrowsePageContent
        boardLabel={ctx.parent.name}
        boardParent={ctx.parent.name}
        initialPage={page}
        initialResources={resources}
        initialTotalCount={total_count}
      />
    </Suspense>
  );
}

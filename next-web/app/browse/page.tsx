import { Metadata } from "next";
import { Suspense } from "react";
import { getTranslations } from "next-intl/server";

import { browseResources } from "@/app/api/graphql/service";
import { BrowsePageContent } from "@/components/BrowsePageContent";
import { BrowseResourceListSkeleton } from "@/components/BrowseResourceListSkeleton";
import { BrowsePageToolbar } from "@/components/BrowsePageToolbar";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { FloatTool } from "@/components/FloatTool";
import { findBoardChild } from "@/config/boards";
import { BROWSE_PAGE_MAX, BROWSE_PAGE_SIZE } from "@/config/constant";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: { board?: string; board_fid?: string; board_parent?: string };
}): Promise<Metadata> {
  const t = await getTranslations();
  const label =
    searchParams.board ||
    searchParams.board_parent ||
    findBoardChild(searchParams.board_fid || "")?.name ||
    "";

  return {
    title: label ? `${label} · ${t("Browse.title")}` : t("Browse.title"),
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

export default async function BrowsePage({
  searchParams,
}: {
  searchParams: {
    p?: string;
    board_fid?: string;
    board?: string;
    board_parent?: string;
  };
}) {
  const page = Math.min(
    Math.max(Number(searchParams.p) || 1, 1),
    BROWSE_PAGE_MAX,
  );
  const boardFid = (searchParams.board_fid || "").trim() || undefined;
  const board = (searchParams.board || "").trim() || undefined;
  const boardParent = (searchParams.board_parent || "").trim() || undefined;
  const boardLabel =
    board ||
    boardParent ||
    findBoardChild(boardFid || "")?.name ||
    undefined;

  const { resources, total_count } = await browseResources(null, {
    limit: BROWSE_PAGE_SIZE,
    offset: (page - 1) * BROWSE_PAGE_SIZE,
    board_fid: boardFid,
    board,
    board_parent: boardParent,
  });

  return (
    <section className="mx-auto flex w-full flex-col gap-4 px-3 py-3 md:max-w-3xl md:gap-5 md:py-8 lg:max-w-4xl">
      <div className="mb-2 flex items-center md:mb-3">
        <SiteLogoLink />
        <SearchInput />
        <SettingsNavLink />
      </div>

      <Suspense fallback={<BrowseContentFallback />}>
        <BrowsePageContent
          boardFid={boardFid}
          boardLabel={boardLabel}
          boardParent={boardParent}
          initialPage={page}
          initialResources={resources}
          initialTotalCount={total_count}
        />
      </Suspense>

      <FloatTool />
    </section>
  );
}

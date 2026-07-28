import { Metadata } from "next";
import { Suspense } from "react";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { browseResources, listPrefixCodes } from "@/app/api/graphql/service";
import { BrowsePageContent } from "@/components/BrowsePageContent";
import { BrowseResourceListSkeleton } from "@/components/BrowseResourceListSkeleton";
import { BrowsePageToolbar } from "@/components/BrowsePageToolbar";
import { ForumShell } from "@/components/ForumShell";
import { PrefixCodeIndex } from "@/components/PrefixCodeIndex";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { FloatTool } from "@/components/FloatTool";
import {
  boardParentBrowseHref,
  boardPath,
  categoryHref,
  findSubtype,
  legacyFidRedirect,
  makeBoardKey,
} from "@/config/boards";
import { prefixNote } from "@/config/av-makers";
import { BROWSE_PAGE_MAX, BROWSE_PAGE_SIZE } from "@/config/constant";

export const dynamic = "force-dynamic";

const PREFIX_CODE_PAGE_SIZE = 120;

export async function generateMetadata({
  params,
}: {
  params: { fid: string; typeid: string };
}): Promise<Metadata> {
  const fid = decodeURIComponent(params.fid);
  const typeid = decodeURIComponent(params.typeid);
  const ctx = findSubtype(fid, typeid);
  const t = await getTranslations();
  const label = ctx?.child?.type_name || ctx?.child?.name || "";
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

export default async function SubtypeBrowsePage({
  params,
  searchParams,
}: {
  params: { fid: string; typeid: string };
  searchParams: { p?: string };
}) {
  const fid = decodeURIComponent(params.fid);
  const typeid = decodeURIComponent(params.typeid);
  const legacy = legacyFidRedirect(fid);
  if (legacy) {
    redirect(legacy);
  }
  const ctx = findSubtype(fid, typeid);
  if (!ctx?.child) notFound();

  const boardLabel = ctx.child.type_name || ctx.child.name;
  const page = Math.min(
    Math.max(Number(searchParams.p) || 1, 1),
    BROWSE_PAGE_MAX,
  );

  const crumbs = [
    {
      label: ctx.category.category,
      href: categoryHref(ctx.categoryIndex),
    },
    ...(ctx.group
      ? [
          {
            label: ctx.group.name,
            href: boardParentBrowseHref(ctx.group),
          },
        ]
      : []),
    { label: ctx.parent.name, href: boardPath(fid) },
    { label: boardLabel },
  ];

  // 番号前缀：展示库内已有编号索引
  if (ctx.child.search_keyword) {
    const prefix = ctx.child.search_keyword.trim();
    const t = await getTranslations();
    const note = prefixNote(ctx.child.board_name || ctx.parent.name, prefix);
    const { codes, total_codes, matched_rows } = await listPrefixCodes(prefix, {
      limit: PREFIX_CODE_PAGE_SIZE,
      offset: (page - 1) * PREFIX_CODE_PAGE_SIZE,
    });
    const searchAll = new URLSearchParams();
    searchAll.set("keyword", prefix);
    searchAll.set("matchMode", "exact");

    return (
      <>
        <div className="mx-auto flex w-full max-w-6xl items-center gap-1 px-3 pt-3 md:px-4 lg:max-w-7xl">
          <SiteLogoLink />
          <SearchInput />
          <SettingsNavLink />
        </div>
        <ForumShell
          activeCategoryIndex={ctx.categoryIndex}
          activeFid={fid}
          activeTypeid={typeid}
          crumbs={crumbs}
        >
          <PrefixCodeIndex
            codes={codes}
            matchedRows={matched_rows}
            note={note}
            page={page}
            pageSize={PREFIX_CODE_PAGE_SIZE}
            prefix={prefix}
            searchAllHref={`/search?${searchAll.toString()}`}
            totalCodes={total_codes}
            labels={{
              guide: t("Boards.prefix_code_guide"),
              total: t("Boards.prefix_code_total"),
              empty: t("Boards.prefix_code_empty"),
              searchAll: t("Boards.prefix_code_search_all"),
              resources: t("Boards.prefix_code_resources"),
              pageOf: t("Boards.prefix_code_page"),
              prev: t("Boards.prefix_code_prev"),
              next: t("Boards.prefix_code_next"),
            }}
          />
        </ForumShell>
        <FloatTool />
      </>
    );
  }

  const boardFid = makeBoardKey(fid, typeid);
  const { resources, total_count } = await browseResources(null, {
    limit: BROWSE_PAGE_SIZE,
    offset: (page - 1) * BROWSE_PAGE_SIZE,
    board_fid: boardFid,
    board: ctx.child.name,
  });

  return (
    <>
      <div className="mx-auto flex w-full max-w-6xl items-center gap-1 px-3 pt-3 md:px-4 lg:max-w-7xl">
        <SiteLogoLink />
        <SearchInput />
        <SettingsNavLink />
      </div>
      <ForumShell
        activeCategoryIndex={ctx.categoryIndex}
        activeFid={fid}
        activeTypeid={typeid}
        crumbs={crumbs}
      >
        <Suspense fallback={<BrowseContentFallback />}>
          <BrowsePageContent
            boardFid={boardFid}
            boardLabel={boardLabel}
            initialPage={page}
            initialResources={resources}
            initialTotalCount={total_count}
          />
        </Suspense>
      </ForumShell>
      <FloatTool />
    </>
  );
}

import { Metadata } from "next";
import { Suspense } from "react";
import { getTranslations } from "next-intl/server";

import { listActressResources } from "@/app/api/graphql/service";
import { PrefixResourceList } from "@/components/PrefixResourceList";
import { PrefixResourceListSkeleton } from "@/components/PrefixResourceListSkeleton";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { FloatTool } from "@/components/FloatTool";
import { MobileShellHeader, MobileViewportScroll } from "@/components/MobileViewportScroll";
import { BROWSE_PAGE_MAX, PREFIX_CODE_PAGE_SIZE } from "@/config/constant";

export const dynamic = "force-dynamic";

type ActressSearchParams = {
  keyword?: string;
  p?: string;
  jp?: string;
};

export async function generateMetadata({
  searchParams,
}: {
  searchParams: ActressSearchParams;
}): Promise<Metadata> {
  const t = await getTranslations();
  const keyword = String(searchParams.keyword || "").trim();
  return {
    title: keyword
      ? `${keyword} · ${t("Search.mode.actress")}`
      : t("Search.mode.actress"),
  };
}

async function ActressResults({
  keyword,
  page,
  japanPrefs,
}: {
  keyword: string;
  page: number;
  japanPrefs: boolean;
}) {
  const t = await getTranslations();
  const { items, total_count } = await listActressResources(keyword, {
    limit: PREFIX_CODE_PAGE_SIZE,
    offset: (page - 1) * PREFIX_CODE_PAGE_SIZE,
  });

  const qs = (p: number) => {
    const params = new URLSearchParams();
    params.set("keyword", keyword);
    if (p > 1) params.set("p", String(p));
    if (japanPrefs) params.set("jp", "1");
    return `?${params.toString()}`;
  };

  return (
    <PrefixResourceList
      buildPageHref={qs}
      items={items}
      labels={{
        empty: t("Search.actress_empty"),
        prev: t("Search.actress_prev"),
        next: t("Search.actress_next"),
        pageOf: t("Search.page_of", {
          page,
          total: Math.max(1, Math.ceil(total_count / PREFIX_CODE_PAGE_SIZE)),
        }),
      }}
      page={page}
      pageSize={PREFIX_CODE_PAGE_SIZE}
      prefix={t("Search.actress_results", {
        name: keyword,
        count: String(total_count),
      })}
      totalCount={total_count}
    />
  );
}

export default async function ActressSearchPage({
  searchParams,
}: {
  searchParams: ActressSearchParams;
}) {
  const keyword = String(searchParams.keyword || "").trim();
  const page = Math.min(
    Math.max(Number(searchParams.p) || 1, 1),
    BROWSE_PAGE_MAX,
  );
  const japanPrefs = searchParams.jp === "1";
  const t = await getTranslations();

  return (
    <>
      <MobileViewportScroll>
        <MobileShellHeader>
          <div className="mx-auto flex w-full max-w-6xl items-center gap-1 px-3 pt-2 pb-2 md:px-4 md:pt-3 lg:max-w-7xl">
            <SiteLogoLink />
            <SearchInput
              defaultSearchKind="actress"
              defaultValue={keyword}
              japanPrefs={japanPrefs}
            />
            <SettingsNavLink />
          </div>
        </MobileShellHeader>
        <div className="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col overflow-hidden px-3 py-3 md:overflow-visible md:px-4 md:py-6 lg:max-w-7xl">
          {!keyword ? (
            <div className="rounded-2xl border border-dashed border-default-300/80 px-4 py-12 text-center text-sm text-default-500 dark:border-slate-600">
              {t("Search.placeholderActress")}
            </div>
          ) : (
            <Suspense
              fallback={
                <PrefixResourceListSkeleton count={12} prefix={keyword} />
              }
            >
              <ActressResults
                japanPrefs={japanPrefs}
                keyword={keyword}
                page={page}
              />
            </Suspense>
          )}
        </div>
      </MobileViewportScroll>
      <FloatTool />
    </>
  );
}

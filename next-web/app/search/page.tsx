import { cookies } from "next/headers";
import { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import SearchResultsList from "@/components/SearchResultsList";
import { PageSearchHeader } from "@/components/PageSearchHeader";
import type { ForumCrumb } from "@/components/ForumBreadcrumb";
import { search as searchResources } from "@/app/api/graphql/service";
import {
  SEARCH_PAGE_SIZE,
  DEFAULT_FILTER_TIME,
  DEFAULT_FILTER_SIZE,
  SEARCH_PAGE_MAX,
  normalizeMatchMode,
  normalizeSortType,
  FilterTime,
  FilterSize,
} from "@/config/constant";
import {
  BROWSE_PREFS_COOKIE,
  parseBrowsePrefsCookie,
} from "@/hooks/useBrowsePreferences";
import { boardPath, categoryHref, subtypePath } from "@/config/boards";
import { isFc2Code } from "@/utils/av-code";

export const dynamic = "force-dynamic";

type SearchParams = {
  keyword: string;
  p?: string;
  ps?: string;
  sortType?: string;
  filterTime?: string;
  filterSize?: string;
  matchMode?: string;
  fuzzy?: string;
  /** 日本分区发起的搜索：才套用中文/破解偏好 */
  jp?: string;
};

function resolveSearchOption(searchParams: SearchParams) {
  const page = Math.min(
    Math.max(Number(searchParams.p) || 1, 1),
    SEARCH_PAGE_MAX,
  );
  const pageSize = Math.min(
    Math.max(Number(searchParams.ps) || SEARCH_PAGE_SIZE, 1),
    SEARCH_PAGE_SIZE,
  );

  return {
    keyword: searchParams.keyword?.trim() || "",
    p: page,
    ps: pageSize,
    sortType: normalizeSortType(searchParams.sortType),
    filterTime: (searchParams.filterTime || DEFAULT_FILTER_TIME) as FilterTime,
    filterSize: (searchParams.filterSize || DEFAULT_FILTER_SIZE) as FilterSize,
    matchMode: normalizeMatchMode({
      matchMode: searchParams.matchMode,
      fuzzy: searchParams.fuzzy,
    }),
  };
}

/** 日本分区搜索面包屑：尽量还原番号来源 */
function japanSearchCrumbs(keyword: string): ForumCrumb[] {
  const crumbs: ForumCrumb[] = [
    { label: "片区", href: categoryHref(0) },
    { label: "日本", href: boardPath("mk-japan") },
  ];
  const kw = keyword.trim();
  if (isFc2Code(kw) || /^FC2\b/i.test(kw)) {
    crumbs.push({ label: "无码", href: boardPath("mk-uncensored") });
    if (/PPV/i.test(kw)) {
      crumbs.push({
        label: "FC2PPV",
        href: subtypePath("mk-uncensored", "FC2PPV"),
      });
    } else {
      crumbs.push({
        label: "FC2",
        href: subtypePath("mk-uncensored", "FC2"),
      });
    }
  }
  crumbs.push({ label: "搜索页" });
  return crumbs;
}

export async function generateMetadata({
  searchParams: { keyword },
}: {
  searchParams: { keyword: string };
}): Promise<Metadata> {
  const t = await getTranslations();

  return {
    title: t("Metadata.search.title", { keyword }),
  };
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const searchOption = resolveSearchOption(searchParams);
  const start_time = Date.now();
  const japanScope = searchParams.jp === "1";
  const browsePrefs = japanScope
    ? parseBrowsePrefsCookie(cookies().get(BROWSE_PREFS_COOKIE)?.value)
    : { preferChinese: false, preferCrack: false };

  const data = await searchResources(null, {
    queryInput: {
      keyword: searchOption.keyword,
      limit: searchOption.ps,
      offset: (searchOption.p - 1) * searchOption.ps,
      sortType: searchOption.sortType,
      filterTime: searchOption.filterTime,
      filterSize: searchOption.filterSize,
      matchMode: searchOption.matchMode,
      withTotalCount: true,
      preferChinese: browsePrefs.preferChinese,
      preferCrack: browsePrefs.preferCrack,
    },
  });

  const cost_time = Date.now() - start_time;

  return (
    <div className="w-full md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl">
      <PageSearchHeader
        className="mb-7"
        crumbs={japanScope ? japanSearchCrumbs(searchOption.keyword) : undefined}
        defaultValue={searchOption.keyword}
        japanPrefs={japanScope}
      />
      <SearchResultsList
        cost_time={cost_time}
        japanPrefs={japanScope}
        keywords={data.keywords}
        resultList={data.resources}
        searchOption={searchOption}
        total_count={data.total_count}
      />
    </div>
  );
}

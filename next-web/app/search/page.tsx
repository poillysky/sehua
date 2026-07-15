import { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import SearchResultsList from "@/components/SearchResultsList";
import { SearchInput } from "@/components/SearchInput";
import { SiteLogoLink } from "@/components/SiteLogoLink";
import { SettingsNavLink } from "@/components/SettingsNavLink";
import { search as searchResources } from "@/app/api/graphql/service";
import {
  SEARCH_PAGE_SIZE,
  DEFAULT_FILTER_TIME,
  DEFAULT_FILTER_SIZE,
  SEARCH_PAGE_MAX,
  MatchMode,
  SortType,
  FilterTime,
  FilterSize,
  normalizeMatchMode,
  normalizeSortType,
} from "@/config/constant";

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
    },
  });

  const cost_time = Date.now() - start_time;

  return (
    <div className="w-full md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl">
      <div className="flex items-center mb-7">
        <SiteLogoLink />
        <SearchInput defaultValue={searchOption.keyword} />
        <SettingsNavLink />
      </div>
      <SearchResultsList
        cost_time={cost_time}
        keywords={data.keywords}
        resultList={data.resources}
        searchOption={searchOption}
        total_count={data.total_count}
      />
    </div>
  );
}

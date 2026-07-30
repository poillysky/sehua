import SearchResultsList from "@/components/SearchResultsList";
import { search as searchResources } from "@/app/api/graphql/service";
import {
  DEFAULT_FILTER_SIZE,
  DEFAULT_FILTER_TIME,
  SEARCH_PAGE_SIZE,
  normalizeMatchMode,
  normalizeSortType,
  FilterSize,
  FilterTime,
} from "@/config/constant";
import { zoneFolderHref } from "@/lib/zoneFolderModel";

export default async function ZoneFolderSearchResults({
  keyword,
  page,
  categoryIndex,
  folderId,
  sortType,
  filterTime,
  filterSize,
  matchMode,
  pageSize,
}: {
  keyword: string;
  page: number;
  categoryIndex: number;
  folderId: string;
  sortType?: string;
  filterTime?: string;
  filterSize?: string;
  matchMode?: string;
  pageSize?: string;
}) {
  const kw = keyword.trim();
  if (!kw) return null;

  const p = Math.max(page, 1);
  const ps = Math.min(
    Math.max(Number(pageSize) || SEARCH_PAGE_SIZE, 1),
    SEARCH_PAGE_SIZE,
  );
  const resolvedSort = normalizeSortType(sortType);
  const resolvedTime = (filterTime || DEFAULT_FILTER_TIME) as FilterTime;
  const resolvedSize = (filterSize || DEFAULT_FILTER_SIZE) as FilterSize;
  const resolvedMatch = normalizeMatchMode({ matchMode });

  const start = Date.now();
  const data = await searchResources(null, {
    queryInput: {
      keyword: kw,
      limit: ps,
      offset: (p - 1) * ps,
      sortType: resolvedSort,
      filterTime: resolvedTime,
      filterSize: resolvedSize,
      matchMode: resolvedMatch,
      withTotalCount: true,
      preferChinese: false,
      preferCrack: false,
    },
  });
  const cost_time = Date.now() - start;

  return (
    <SearchResultsList
      cost_time={cost_time}
      keywords={data.keywords}
      resultList={data.resources}
      resultsBasePath={zoneFolderHref(categoryIndex, folderId)}
      searchOption={{
        keyword: kw,
        p,
        ps,
        sortType: resolvedSort,
        filterTime: resolvedTime,
        filterSize: resolvedSize,
        matchMode: resolvedMatch,
      }}
      total_count={data.total_count}
    />
  );
}

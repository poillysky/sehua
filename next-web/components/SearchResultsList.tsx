"use client";
import { useRouter } from "next/navigation";
import { Pagination, Select, SelectItem, SelectSection } from "@nextui-org/react";
import { useTranslations } from "next-intl";
import { useIsSSR } from "@react-aria/ssr";

import SearchResultsItem from "./SearchResultsItem";

import { SearchResultsListProps } from "@/types";
import { $env } from "@/utils";
import {
  SEARCH_PARAMS,
  SEARCH_FILTER_ORDER,
  SEARCH_PAGE_MAX,
  FilterSize,
  FilterTime,
  MatchMode,
  SortType,
} from "@/config/constant";
import { saveSearchPreferences } from "@/hooks/useSearchPreferences";

type SearchOption = {
  keyword: string;
  p: number;
  ps: number;
  sortType: SortType;
  filterTime: FilterTime;
  filterSize: FilterSize;
  matchMode: MatchMode;
};

export default function SearchResultsList({
  resultList,
  keywords,
  cost_time = 0,
  total_count = 0,
  searchOption,
}: {
  resultList: SearchResultsListProps["resources"];
  keywords: string[];
  cost_time: number;
  total_count: number;
  searchOption: SearchOption;
}) {
  const router = useRouter();
  const isSSR = useIsSSR();
  const t = useTranslations();

  const handleFilterChange = (type: keyof typeof SEARCH_PARAMS, value: string) => {
    const updatedSearchOption = {
      ...searchOption,
      [type]: value,
    };

    if (type === "sortType") {
      saveSearchPreferences({ sortType: value as SortType });
    }

    if (type === "matchMode") {
      saveSearchPreferences({ matchMode: value as MatchMode });
    }

    handlePageChange(1, updatedSearchOption);
  };

  const handlePageChange = (page: number, newSearchOption: SearchOption) => {
    const params = new URLSearchParams();

    params.set("keyword", newSearchOption.keyword);
    params.set("p", String(page));
    params.set("ps", String(newSearchOption.ps));
    params.set("sortType", newSearchOption.sortType);
    params.set("filterTime", newSearchOption.filterTime);
    params.set("filterSize", newSearchOption.filterSize);
    params.set("matchMode", newSearchOption.matchMode);

    router.push(`/search?${params.toString()}`);
  };

  const pagiConf = {
    page: searchOption.p,
    total: Math.min(Math.ceil(total_count / searchOption.ps), SEARCH_PAGE_MAX),
    siblinds: $env.isMobile ? 1 : 3,
  };

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 my-4">
        {SEARCH_FILTER_ORDER.map((key) => {
          const options = SEARCH_PARAMS[key];
          const currentValue = searchOption[key];

          return (
            <Select
              key={key}
              aria-label={t(`Search.filterLabel.${key}`)}
              className="w-full"
              classNames={{
                trigger: "h-10 min-h-10 md:h-11 md:min-h-11 bg-default-100",
                value: "text-xs md:text-sm",
              }}
              popoverProps={{
                classNames: {
                  content: "bg-opacity-90 backdrop-blur-sm min-w-fit px-1",
                },
              }}
              renderValue={() => (
                <span className="text-xs md:text-sm">
                  {t(`Search.${key}.${currentValue}`)}
                </span>
              )}
              selectedKeys={[currentValue]}
              size="sm"
              onChange={(e) => handleFilterChange(key, e.target.value)}
            >
              <SelectSection title={t(`Search.filterLabel.${key}`)}>
                {options.map((item) => (
                  <SelectItem
                    key={item}
                    className="w-full !bg-opacity-60"
                    classNames={{
                      title: "text-xs md:text-sm",
                    }}
                  >
                    {t(`Search.${key}.${item}`)}
                  </SelectItem>
                ))}
              </SelectSection>
            </Select>
          );
        })}
      </div>

      <div className="text-sm text-gray-500 mb-4">
        {t("Search.results_found", { count: total_count })}

        {cost_time > 0 && (
          <span className="ml-1 text-xs">
            {t("Search.cost_time", { cost_time: cost_time })}
          </span>
        )}
      </div>

      {resultList.map((item) => (
        <div key={item.hash} className="mb-4">
          <SearchResultsItem item={item} keywords={keywords} />
        </div>
      ))}

      {!isSSR && pagiConf.total > 1 && (
        <Pagination
          key={`pagi_${Object.values(searchOption).join("_")}`}
          className="flex justify-center"
          classNames={{
            wrapper: "gap-x-2",
          }}
          initialPage={pagiConf.page}
          page={pagiConf.page}
          showControls={$env.isDesktop}
          siblings={pagiConf.siblinds}
          size={$env.isMobile ? "lg" : "md"}
          total={pagiConf.total}
          onChange={(page) => handlePageChange(page, searchOption)}
        />
      )}
    </>
  );
}

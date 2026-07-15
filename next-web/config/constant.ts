// ED2K 搜索参数
export const SEARCH_PARAMS = {
  sortType: ["default", "size", "count", "date"],
  filterTime: ["all", "gt-1day", "gt-7day", "gt-31day", "gt-365day"],
  filterSize: [
    "all",
    "lt100mb",
    "gt100mb-lt500mb",
    "gt500mb-lt1gb",
    "gt1gb-lt5gb",
    "gt5gb",
  ],
  matchMode: ["smart", "exact", "fuzzy"],
} as const;

export const SEARCH_FILTER_ORDER = [
  "sortType",
  "filterTime",
  "filterSize",
  "matchMode",
] as const;

export type SortType = (typeof SEARCH_PARAMS.sortType)[number];
export type FilterSize = (typeof SEARCH_PARAMS.filterSize)[number];
export type FilterTime = (typeof SEARCH_PARAMS.filterTime)[number];
export type MatchMode = (typeof SEARCH_PARAMS.matchMode)[number];

// Tokenizer for search keywords
export const SEARCH_KEYWORD_SPLIT_REGEX =
  /[.,!?;—()\[\]{}<>@#%^&*~`"'|\-，。！？；“”‘’“”「」『』《》、【】……（）·　\s]/g;

// Using for Search page
export const SEARCH_DISPLAY_FILES_MAX = 10;
export const SEARCH_KEYWORD_LENGTH_MIN = 2;
export const SEARCH_KEYWORD_LENGTH_MAX = 100;
export const SEARCH_PAGE_SIZE = 10;
export const SEARCH_PAGE_MAX = 100;

export const DEFAULT_SORT_TYPE: SortType = "default";
export const DEFAULT_FILTER_TIME: FilterTime = "all";
export const DEFAULT_FILTER_SIZE: FilterSize = "all";
export const DEFAULT_MATCH_MODE: MatchMode = "smart";

// TODO: Support UI_HIDE_PADDING_FILE
export const UI_HIDE_PADDING_FILE = true;

export const UI_BACKGROUND_ANIMATION = true;

export const UI_BREAKPOINTS = {
  xs: "(max-width: 649px)",
  md: "(min-width: 960px)",
  lg: "(min-width: 1280px)",
  xl: "(min-width: 1400px)",
};

export function normalizeSortType(sortType?: string): SortType {
  if (
    sortType &&
    (SEARCH_PARAMS.sortType as readonly string[]).includes(sortType)
  ) {
    return sortType as SortType;
  }

  return DEFAULT_SORT_TYPE;
}

export function resolveSortTypeForQuery(sortType: SortType) {
  return sortType === "default" ? "relevance" : sortType;
}

export function normalizeMatchMode(options: {
  matchMode?: string;
  fuzzy?: boolean | string;
}): MatchMode {
  if (
    options.matchMode &&
    (SEARCH_PARAMS.matchMode as readonly string[]).includes(options.matchMode)
  ) {
    return options.matchMode as MatchMode;
  }

  if (options.fuzzy === true || options.fuzzy === "1") {
    return "fuzzy";
  }

  return DEFAULT_MATCH_MODE;
}

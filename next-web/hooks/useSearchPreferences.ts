import {
  DEFAULT_MATCH_MODE,
  DEFAULT_SORT_TYPE,
  MatchMode,
  SortType,
} from "@/config/constant";

const STORAGE_KEY = "ed2k-search-preferences";

export type SearchKind = "resource" | "actress";

export type SearchPreferences = {
  sortType: SortType;
  matchMode: MatchMode;
  searchKind: SearchKind;
};

const DEFAULT_SEARCH_KIND: SearchKind = "resource";

function normalizeSearchKind(v: unknown): SearchKind {
  return v === "actress" ? "actress" : "resource";
}

export function getSearchPreferences(): SearchPreferences {
  if (typeof window === "undefined") {
    return {
      sortType: DEFAULT_SORT_TYPE,
      matchMode: DEFAULT_MATCH_MODE,
      searchKind: DEFAULT_SEARCH_KIND,
    };
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY);

    if (!raw) {
      return {
        sortType: DEFAULT_SORT_TYPE,
        matchMode: DEFAULT_MATCH_MODE,
        searchKind: DEFAULT_SEARCH_KIND,
      };
    }

    const parsed = JSON.parse(raw);

    return {
      sortType: parsed.sortType || DEFAULT_SORT_TYPE,
      matchMode: parsed.matchMode || DEFAULT_MATCH_MODE,
      searchKind: normalizeSearchKind(parsed.searchKind),
    };
  } catch {
    return {
      sortType: DEFAULT_SORT_TYPE,
      matchMode: DEFAULT_MATCH_MODE,
      searchKind: DEFAULT_SEARCH_KIND,
    };
  }
}

export function saveSearchPreferences(preferences: Partial<SearchPreferences>) {
  if (typeof window === "undefined") {
    return;
  }

  const current = getSearchPreferences();

  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      ...current,
      ...preferences,
    }),
  );
}

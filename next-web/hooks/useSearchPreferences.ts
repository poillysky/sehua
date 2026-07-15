import {
  DEFAULT_MATCH_MODE,
  DEFAULT_SORT_TYPE,
  MatchMode,
  SortType,
} from "@/config/constant";

const STORAGE_KEY = "ed2k-search-preferences";

export type SearchPreferences = {
  sortType: SortType;
  matchMode: MatchMode;
};

export function getSearchPreferences(): SearchPreferences {
  if (typeof window === "undefined") {
    return { sortType: DEFAULT_SORT_TYPE, matchMode: DEFAULT_MATCH_MODE };
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY);

    if (!raw) {
      return { sortType: DEFAULT_SORT_TYPE, matchMode: DEFAULT_MATCH_MODE };
    }

    const parsed = JSON.parse(raw);

    return {
      sortType: parsed.sortType || DEFAULT_SORT_TYPE,
      matchMode: parsed.matchMode || DEFAULT_MATCH_MODE,
    };
  } catch {
    return { sortType: DEFAULT_SORT_TYPE, matchMode: DEFAULT_MATCH_MODE };
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

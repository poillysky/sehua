import { Cookie } from "@/utils";

export type BrowsePreferences = {
  preferChinese: boolean;
  preferCrack: boolean;
};

const STORAGE_KEY = "ed2k-browse-preferences";
export const BROWSE_PREFS_COOKIE = "ed2k-browse-prefs";

export const DEFAULT_BROWSE_PREFERENCES: BrowsePreferences = {
  preferChinese: false,
  preferCrack: false,
};

function normalizePrefs(raw: unknown): BrowsePreferences {
  if (!raw || typeof raw !== "object") {
    return { ...DEFAULT_BROWSE_PREFERENCES };
  }
  const obj = raw as Record<string, unknown>;
  return {
    preferChinese: Boolean(obj.preferChinese),
    preferCrack: Boolean(obj.preferCrack),
  };
}

export function parseBrowsePrefsCookie(
  value?: string | null,
): BrowsePreferences {
  if (!value) return { ...DEFAULT_BROWSE_PREFERENCES };
  try {
    return normalizePrefs(JSON.parse(value));
  } catch {
    return { ...DEFAULT_BROWSE_PREFERENCES };
  }
}

export function getBrowsePreferences(): BrowsePreferences {
  if (typeof window === "undefined") {
    return { ...DEFAULT_BROWSE_PREFERENCES };
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return normalizePrefs(JSON.parse(raw));
  } catch {
    /* fall through */
  }

  return parseBrowsePrefsCookie(Cookie.get(BROWSE_PREFS_COOKIE));
}

export function saveBrowsePreferences(
  preferences: Partial<BrowsePreferences>,
): BrowsePreferences {
  const next = {
    ...getBrowsePreferences(),
    ...preferences,
  };

  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* ignore quota */
    }
    Cookie.set(BROWSE_PREFS_COOKIE, JSON.stringify(next), {
      path: "/",
      expires: 365,
    });
  }

  return next;
}

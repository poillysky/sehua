type CacheEntry = {
  data: unknown;
  expires: number;
};

const cache = new Map<string, CacheEntry>();
const TTL_MS = 5 * 60 * 1000;
const MAX_ENTRIES = 200;

export function getSearchCacheKey(params: Record<string, unknown>) {
  return JSON.stringify(params);
}

export function getCachedSearch<T>(key: string): T | null {
  const entry = cache.get(key);

  if (!entry) {
    return null;
  }

  if (entry.expires <= Date.now()) {
    cache.delete(key);

    return null;
  }

  return entry.data as T;
}

export function setCachedSearch(key: string, data: unknown) {
  if (cache.size >= MAX_ENTRIES) {
    const oldestKey = cache.keys().next().value;

    if (oldestKey) {
      cache.delete(oldestKey);
    }
  }

  cache.set(key, {
    data,
    expires: Date.now() + TTL_MS,
  });
}

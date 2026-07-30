export type PrefixCodeIndexItem = {
  code: string;
  coverUrl: string | null;
  coverUrls: string[];
};

export type PrefixCodeIndex = {
  items: PrefixCodeIndexItem[];
  matchedRows: number;
};

type CacheEntry = {
  data: PrefixCodeIndex;
  expires: number;
};

const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<PrefixCodeIndex>>();

/** 番号索引：扫描较重，缓存稍长；改归并/封面规则时升版本 */
const CACHE_VER = "v14-prefix-like";
const TTL_MS = 10 * 60 * 1000;
const MAX_ENTRIES = 300;

export function getCachedPrefixCodes(prefix: string): PrefixCodeIndex | null {
  const key = `${CACHE_VER}:${prefix.toUpperCase()}`;
  const entry = cache.get(key);
  if (!entry) return null;
  if (entry.expires <= Date.now()) {
    cache.delete(key);
    return null;
  }
  return entry.data;
}

export function setCachedPrefixCodes(prefix: string, data: PrefixCodeIndex) {
  const key = `${CACHE_VER}:${prefix.toUpperCase()}`;
  if (cache.size >= MAX_ENTRIES && !cache.has(key)) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey) cache.delete(oldestKey);
  }
  cache.set(key, {
    data,
    expires: Date.now() + TTL_MS,
  });
}

/** 同前缀并发只扫一次库 */
export function loadPrefixCodesCached(
  prefix: string,
  loader: () => Promise<PrefixCodeIndex>,
): Promise<PrefixCodeIndex> {
  const key = `${CACHE_VER}:${prefix.toUpperCase()}`;
  const hit = getCachedPrefixCodes(prefix);
  if (hit) return Promise.resolve(hit);

  const pending = inflight.get(key);
  if (pending) return pending;

  const task = loader()
    .then((data) => {
      setCachedPrefixCodes(prefix, data);
      return data;
    })
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, task);
  return task;
}

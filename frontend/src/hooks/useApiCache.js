/**
 * useApiCache -- In-memory API response cache with TTL support.
 *
 * Provides a simple cache layer to avoid redundant API calls.
 * Each cache entry stores data plus its expiry timestamp.
 */

const cache = new Map();

/** Default TTL values in milliseconds */
const DEFAULT_TTL = {
  stockRealtime: 30_000,
  fundNav: 60_000,
  marketOverview: 30_000,
  stockSectors: 30_000,
  fallback: 30_000,
};

/**
 * Build a stable cache key from an endpoint path and optional params.
 * Sorts object keys to ensure consistent key generation.
 */
function buildKey(path, params) {
  if (!params) return path;
  const sorted = Object.keys(params)
    .sort()
    .map((k) => `${k}=${JSON.stringify(params[k])}`)
    .join('&');
  return `${path}?${sorted}`;
}

/**
 * Get a cached value if it exists and has not expired.
 * @param {string} path - API endpoint path
 * @param {Object} [params] - Optional query parameters
 * @returns {*} Cached data or undefined
 */
function getCached(path, params) {
  const key = buildKey(path, params);
  const entry = cache.get(key);
  if (!entry) return undefined;
  if (Date.now() > entry.expiresAt) {
    cache.delete(key);
    return undefined;
  }
  return entry.data;
}

/**
 * Store a value in the cache with a TTL.
 * @param {string} path - API endpoint path
 * @param {*} data - Data to cache
 * @param {number} [ttlMs] - Time-to-live in ms (uses fallback default if omitted)
 * @param {Object} [params] - Optional query parameters
 */
function setCached(path, data, ttlMs, params) {
  const key = buildKey(path, params);
  cache.set(key, {
    data,
    expiresAt: Date.now() + (ttlMs ?? DEFAULT_TTL.fallback),
  });
}

/**
 * Clear all cached entries or a specific entry.
 * @param {string} [path] - If provided, only clear entries matching this path prefix
 */
function clearCache(path) {
  if (!path) {
    cache.clear();
    return;
  }
  for (const key of cache.keys()) {
    if (key === path || key.startsWith(path)) {
      cache.delete(key);
    }
  }
}

export { getCached, setCached, clearCache, DEFAULT_TTL };

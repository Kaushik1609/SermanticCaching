/**
 * CacheIQ API client — the single file that calls fetch().
 * Intelligently resolves the API base URL:
 * - When served from FastAPI (e.g. port 8080 or 8000), uses relative "/api"
 * - When served from a separate dev server (e.g. Live Server port 5500, 3000, 5173) or file://,
 *   targets "http://127.0.0.1:8080/api"
 */
const BASE = (function getApiBase() {
  if (typeof window !== "undefined" && window.location) {
    if (window.location.protocol === "file:") {
      return "http://127.0.0.1:8080/api";
    }
    const port = window.location.port;
    if (port && port !== "8080" && port !== "8000") {
      const hostname = window.location.hostname || "127.0.0.1";
      return "http://" + hostname + ":8080/api";
    }
  }
  return "/api";
})();

if (typeof window !== "undefined") {
  window.CACHEIQ_API_BASE = BASE;
}

async function call(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  try {
    const res = await fetch(BASE + path, { ...options, headers });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error?.message || res.statusText);
    return data;
  } catch (err) {
    console.error("CacheIQ API Error [" + BASE + path + "]:", err);
    throw err;
  }
}

/**
 * POST /api/query — send a query through the cache pipeline.
 */
function sendQuery(query, strategy, contextKey) {
  strategy = strategy || "semantic_verified";
  contextKey = contextKey || "default";
  return call("/query", {
    method: "POST",
    body: JSON.stringify({ query: query, strategy: strategy, context_key: contextKey })
  });
}

/**
 * GET /api/health — liveness check, DB status, model loaded, llm_mode.
 */
function getHealth() {
  return call("/health");
}

/**
 * GET /api/stats — live counters (hits, misses, latencies, cost saved).
 */
function getStats() {
  return call("/stats");
}

/**
 * GET /api/config — thresholds, model, llm_mode, price assumptions.
 */
function getConfig() {
  return call("/config");
}

/**
 * GET /api/entries — list cache entries with pagination.
 */
function getEntries(limit, offset) {
  limit = limit || 50;
  offset = offset || 0;
  return call("/entries?limit=" + limit + "&offset=" + offset);
}

/**
 * POST /api/entries/{id}/invalidate — mark an entry INVALIDATED.
 */
function invalidateEntry(id, adminKey) {
  return call("/entries/" + id + "/invalidate", {
    method: "POST",
    headers: { "X-Admin-Key": adminKey }
  });
}

/**
 * POST /api/admin/reset — clear cache + logs for a clean demo.
 */
function adminReset(adminKey) {
  return call("/admin/reset", {
    method: "POST",
    headers: { "X-Admin-Key": adminKey }
  });
}

/**
 * POST /api/arena/run — run strategies A-D on the eval dataset.
 */
function runArena() {
  return call("/arena/run", { method: "POST" });
}

/**
 * GET /api/arena/latest — last arena result.
 */
function getArenaLatest() {
  return call("/arena/latest");
}


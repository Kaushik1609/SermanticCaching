/**
 * CacheIQ API client — the single file that calls fetch().
 * Base URL is relative (/api/...) so no CORS setup needed.
 */
const BASE = "/api";

async function call(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  const res = await fetch(BASE + path, { ...options, headers });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || res.statusText);
  return data;
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


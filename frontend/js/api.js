/**
 * CacheIQ API client — the single file that calls fetch().
 * Intelligently resolves the API base URL:
 * - Checks URL parameter: ?backend=https://...
 * - Checks localStorage: cacheiq_backend_url
 * - Global override: window.CACHEIQ_BACKEND_URL
 * - Localhost / 127.0.0.1 on ports 8080/8000 uses "/api"
 * - Localhost on dev ports (5500, 3000, 5173) or file:// uses "http://127.0.0.1:8080/api"
 * - Production cloud deployments (e.g. Vercel) default to "/api" (proxied to Render via vercel.json)
 *   or fallback directly to "https://cacheiq-backend.onrender.com/api"
 */
const DEFAULT_PROD_BACKEND = "https://cacheiq-backend.onrender.com/api";

function getApiBase() {
  if (typeof window !== "undefined" && window.location) {
    // 1. Query parameter override (?backend=https://...)
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const paramBackend = urlParams.get("backend");
      if (paramBackend) {
        const clean = paramBackend.trim().replace(/\/+$/, "");
        localStorage.setItem("cacheiq_backend_url", clean);
        return clean.endsWith("/api") ? clean : clean + "/api";
      }
    } catch (e) {}

    // 2. Saved backend URL in localStorage
    try {
      const saved = localStorage.getItem("cacheiq_backend_url");
      if (saved && saved.trim()) {
        const clean = saved.trim().replace(/\/+$/, "");
        return clean.endsWith("/api") ? clean : clean + "/api";
      }
    } catch (e) {}

    // 3. Global window override
    if (window.CACHEIQ_BACKEND_URL && window.CACHEIQ_BACKEND_URL.trim()) {
      const clean = window.CACHEIQ_BACKEND_URL.trim().replace(/\/+$/, "");
      return clean.endsWith("/api") ? clean : clean + "/api";
    }

    // 4. Local file origin
    if (window.location.protocol === "file:") {
      return "http://127.0.0.1:8080/api";
    }

    // 5. Local dev servers
    const hostname = window.location.hostname || "127.0.0.1";
    const port = window.location.port;
    const isLocal = hostname === "localhost" || hostname === "127.0.0.1";

    if (isLocal) {
      if (port && port !== "8080" && port !== "8000") {
        return "http://" + hostname + ":8080/api";
      }
      return "/api";
    }

    // 6. When hosted on cloud (e.g. Vercel), relative "/api" is rewrote by vercel.json.
    // If not rewritten, DEFAULT_PROD_BACKEND acts as direct fallback.
    return "/api";
  }
  return "/api";
}

let BASE = getApiBase();

function setApiBase(url) {
  if (!url || !url.trim()) {
    try { localStorage.removeItem("cacheiq_backend_url"); } catch (e) {}
  } else {
    const clean = url.trim().replace(/\/+$/, "");
    try { localStorage.setItem("cacheiq_backend_url", clean); } catch (e) {}
  }
  BASE = getApiBase();
  if (typeof window !== "undefined") {
    window.CACHEIQ_API_BASE = BASE;
  }
  return BASE;
}

function updateConnectionStatus(isOk, details) {
  if (typeof document === "undefined") return;
  const badge = document.getElementById("db-status-badge");
  if (!badge) return;
  badge.style.cursor = "pointer";
  if (isOk) {
    badge.innerHTML = '<span class="h-2 w-2 rounded-full bg-emerald-500 inline-block"></span><span>Postgres · pgvector connected</span>';
    badge.className = "inline-flex items-center gap-1.5 px-3 py-1 rounded bg-surface-container-low border border-emerald-500/40 font-code-sm text-xs text-on-surface cursor-pointer hover:bg-surface-container transition-colors";
    badge.title = "Connected to backend: " + BASE + "\n(Click to change Backend URL)";
  } else {
    badge.innerHTML = '<span class="h-2 w-2 rounded-full bg-amber-500 inline-block animate-pulse"></span><span>Backend Disconnected · Click to Connect</span>';
    badge.className = "inline-flex items-center gap-1.5 px-3 py-1 rounded bg-amber-500/10 border border-amber-500/50 font-code-sm text-xs text-amber-600 dark:text-amber-400 cursor-pointer hover:bg-amber-500/20 transition-colors";
    badge.title = (details || "Backend unreachable at " + BASE) + "\n(Click to configure Backend URL)";
  }
}

function initStatusBadgeListener() {
  if (typeof document === "undefined") return;
  const badge = document.getElementById("db-status-badge");
  if (!badge || badge.dataset.hasListener) return;
  badge.dataset.hasListener = "true";
  badge.style.cursor = "pointer";
  badge.addEventListener("click", () => {
    let current = "";
    try { current = localStorage.getItem("cacheiq_backend_url") || ""; } catch (e) {}
    const input = window.prompt(
      "CacheIQ Backend Connection Settings\n\n" +
      "Enter the URL where your CacheIQ FastAPI backend is hosted:\n" +
      "Examples:\n" +
      "  - Render / Railway: https://cacheiq-backend.onrender.com\n" +
      "  - Cloudflare Tunnel: https://your-tunnel.trycloudflare.com\n" +
      "  - Localhost (if accessible): http://127.0.0.1:8080\n\n" +
      "Leave blank to restore default.",
      current
    );
    if (input !== null) {
      setApiBase(input);
      window.location.reload();
    }
  });
}

if (typeof window !== "undefined") {
  window.CACHEIQ_API_BASE = BASE;
  window.setCacheiqBackendUrl = setApiBase;
  window.updateConnectionStatus = updateConnectionStatus;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initStatusBadgeListener);
  } else {
    initStatusBadgeListener();
  }
}

async function call(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  let targetUrl = BASE + path;
  try {
    let res = await fetch(targetUrl, { ...options, headers });

    // Automatic fallback if relative /api returns 404 on cloud (e.g. Vercel without rewrites)
    if (
      res.status === 404 &&
      BASE === "/api" &&
      typeof window !== "undefined" &&
      window.location &&
      window.location.hostname !== "localhost" &&
      window.location.hostname !== "127.0.0.1"
    ) {
      BASE = DEFAULT_PROD_BACKEND;
      targetUrl = BASE + path;
      res = await fetch(targetUrl, { ...options, headers });
    }

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    if (!res.ok) {
      if (isJson) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.error?.message || `HTTP ${res.status}: ${res.statusText}`);
      } else {
        const text = await res.text().catch(() => "");
        if (res.status === 404) {
          throw new Error(
            `Backend API not found at "${targetUrl}" (HTTP 404).\n` +
            `The Vercel frontend is not connected to a live backend.\n` +
            `Click the "Backend Disconnected" badge at top-right to set your backend URL, or open http://127.0.0.1:8080/ locally.`
          );
        }
        throw new Error(`HTTP ${res.status} (${res.statusText}): ${text.slice(0, 100)}`);
      }
    }

    if (isJson) {
      return await res.json();
    }
    return await res.text();
  } catch (err) {
    console.error("CacheIQ API Error [" + targetUrl + "]:", err);
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


/**
 * CacheIQ — Chat page logic.
 * Wires the Chat Console (index.html) to the API via api.js functions.
 * PRD §9 DOM id contract: #query-input, #send-btn, #chat-log,
 *   #strategy-select, #badge-outcome, #val-similarity, #val-lookup-ms,
 *   #val-total-ms, #val-reason, #val-explain, #val-matched
 */
(function initChat() {
  // DOM references
  var queryForm = document.getElementById('queryForm');
  var queryInput = document.getElementById('query-input');
  var sendBtn = document.getElementById('send-btn');
  var chatLog = document.getElementById('chat-log');
  var strategySelect = document.getElementById('strategy-select');

  // Inspector panel
  var badgeOutcome = document.getElementById('badge-outcome');
  var valSimilarity = document.getElementById('val-similarity');
  var valSimilarityBar = document.getElementById('val-similarity-bar');
  var valLookupMs = document.getElementById('val-lookup-ms');
  var valTotalMs = document.getElementById('val-total-ms');
  var valReason = document.getElementById('val-reason');
  var valReasonDetail = document.getElementById('val-reason-detail');
  var valExplain = document.getElementById('val-explain');
  var valMatched = document.getElementById('val-matched');
  var valMatchedScore = document.getElementById('val-matched-score');
  var valMatchedId = document.getElementById('val-matched-id');
  var inspectorCard = document.getElementById('inspector-card');
  var inspectorSub = document.getElementById('inspector-sub');
  var inspectorDetail = document.getElementById('inspector-detail');
  var inspectorTokens = document.getElementById('inspector-tokens');
  var inspectorCost = document.getElementById('inspector-cost');

  // Buttons
  var resetSessionBtn = document.getElementById('resetSessionBtn');
  var invalidateBtn = document.getElementById('invalidateBtn');

  var currentMatchedEntryId = null;

  function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /** Sync health endpoint and live stats into the header. */
  function syncHealth() {
    getHealth().then(function(data) {
      var modeEl = document.getElementById('llm-mode-label');
      if (modeEl) {
        modeEl.textContent = data.llm_mode === 'gemini' ? 'Gemini Live' : (data.llm_mode || 'Mock');
      }
    }).catch(function() {});

    getStats().then(function(stats) {
      var savingsEl = document.getElementById('header-savings');
      if (savingsEl && stats.est_cost_saved !== undefined) {
        savingsEl.textContent = '$' + Number(stats.est_cost_saved).toFixed(4);
      }
      var avoidedEl = document.getElementById('footer-calls-avoided');
      if (avoidedEl && stats.llm_calls_avoided !== undefined) {
        avoidedEl.textContent = 'LLM Calls Avoided: ' + stats.llm_calls_avoided;
      }
    }).catch(function() {});
  }

  syncHealth();

  /** Update the inspector panel with API response data. */
  function updateInspector(data) {
    var isHit = data.outcome === 'HIT';

    badgeOutcome.textContent = data.outcome;
    if (isHit) {
      badgeOutcome.className = 'font-metric-display text-2xl font-bold text-emerald-800 leading-none tracking-tight';
      inspectorCard.className = 'flex items-center justify-between p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-200 transition-colors';
      inspectorSub.textContent = 'DECISION MATCHED';
      inspectorSub.className = 'font-label-caps text-xs text-emerald-800 uppercase tracking-wider font-bold';
      inspectorDetail.textContent = 'Verified semantic match';
      inspectorDetail.className = 'font-code-sm text-xs text-emerald-700';
      inspectorTokens.textContent = 'Saved ~50 tokens';
      inspectorTokens.className = 'font-code-sm text-xs text-emerald-800 font-bold';
      inspectorCost.textContent = '~ $0.0003 avoided';
    } else {
      badgeOutcome.className = 'font-metric-display text-2xl font-bold text-amber-800 leading-none tracking-tight';
      inspectorCard.className = 'flex items-center justify-between p-3.5 rounded-lg bg-amber-500/10 border border-amber-200 transition-colors';
      inspectorSub.textContent = 'CACHE BYPASSED';
      inspectorSub.className = 'font-label-caps text-xs text-amber-800 uppercase tracking-wider font-bold';
      inspectorDetail.textContent = data.reason_code;
      inspectorDetail.className = 'font-code-sm text-xs text-amber-700';
      inspectorTokens.textContent = '0 tokens saved';
      inspectorTokens.className = 'font-code-sm text-xs text-amber-800 font-bold';
      inspectorCost.textContent = 'LLM called';
    }

    var simPercent = data.similarity !== null && data.similarity !== undefined ? Math.round(data.similarity * 100) : null;
    valSimilarity.textContent = simPercent !== null ? simPercent + '%' : '—';
    valSimilarityBar.style.width = (simPercent || 0) + '%';
    valSimilarityBar.className = isHit ? 'bg-emerald-600 h-full rounded-full' : 'bg-outline-variant h-full rounded-full';

    valLookupMs.textContent = data.lookup_ms.toFixed(1) + ' ms';
    valTotalMs.textContent = data.total_ms.toFixed(1) + ' ms';
    valReason.textContent = data.reason_code;
    valReasonDetail.textContent = isHit ? 'vector_sim ≥ 0.85' : 'threshold not met';
    valExplain.textContent = data.explain;

    valMatched.textContent = data.matched_query ? '"' + data.matched_query + '"' : 'No prior candidate matched.';
    valMatchedScore.textContent = data.similarity !== null && data.similarity !== undefined ? 'cos θ ' + data.similarity.toFixed(2) : '—';
    valMatchedId.innerHTML = 'ID: <strong class="text-on-surface">#' + (data.matched_entry_id || '—') + '</strong>';
  }

  /** Build a chat response bubble from API data. */
  function buildResponseBubble(data) {
    var isHit = data.outcome === 'HIT';
    var badgeBg = isHit ? 'bg-emerald-50 border-emerald-300 text-emerald-800' : 'bg-amber-50 border-amber-200 text-amber-800';
    var dotBg = isHit ? 'bg-emerald-600' : 'bg-amber-500';
    var latencyText = isHit
      ? data.lookup_ms.toFixed(1) + ' ms (Cache)'
      : data.total_ms.toFixed(0) + ' ms (' + (data.llm_mode || 'LLM') + ')';
    var cardBorder = isHit
      ? 'border-2 border-primary/40 shadow-md ring-1 ring-primary/20'
      : 'border border-outline-variant/60';
    var hitTag = isHit
      ? '<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-primary/10 text-primary font-code-sm text-[11px] font-semibold">INSPECTING</span>'
      : '<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-surface-container-low text-on-surface-variant font-code-sm text-[11px] font-semibold border border-outline-variant/40">' + escapeHtml(data.reason_code) + '</span>';
    var subInfo = isHit
      ? '<span class="text-primary font-medium">Similarity: ' + Math.round((data.similarity || 0) * 100) + '% (Threshold ≥ 0.85)</span><span>Matched Entry #' + (data.matched_entry_id || '—') + '</span>'
      : '<span class="text-amber-800 font-medium">Stored in cache as #' + (data.matched_entry_id || 'new') + '</span><span>Origin LLM: ' + escapeHtml(data.llm_mode || 'gemini') + '</span>';

    var div = document.createElement('div');
    div.className = 'flex justify-start';
    div.innerHTML =
      '<div class="rounded-2xl rounded-tl-sm bg-surface-container-lowest ' + cardBorder + ' text-on-surface p-4 max-w-xl shadow-sm space-y-2.5">' +
        '<div class="flex items-center justify-between gap-3 text-body-sm pb-1.5 border-b border-outline-variant/30">' +
          '<div class="flex items-center gap-2">' +
            '<div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full ' + badgeBg + ' font-code-sm text-xs font-bold">' +
              '<span class="w-1.5 h-1.5 rounded-full ' + dotBg + ' inline-block"></span>' +
              data.outcome +
            '</div>' +
            hitTag +
          '</div>' +
          '<div class="font-code-sm text-xs text-secondary font-medium flex items-center gap-1">' +
            '<span class="material-symbols-outlined text-[14px]">' + (isHit ? 'bolt' : 'dns') + '</span>' +
            '<span>' + latencyText + '</span>' +
          '</div>' +
        '</div>' +
        '<p class="font-body-md leading-relaxed text-on-surface whitespace-pre-wrap">' + escapeHtml(data.answer) + '</p>' +
        '<div class="pt-1 flex items-center justify-between text-on-surface-variant text-xs font-code-sm bg-surface-container-low px-2 py-1 rounded">' +
          subInfo +
        '</div>' +
      '</div>';
    return div;
  }

  // Form submission
  if (queryForm && queryInput && chatLog) {
    queryForm.addEventListener('submit', function(e) {
      e.preventDefault();
      var query = queryInput.value.trim();
      if (!query) return;

      var strategy = strategySelect ? strategySelect.value : 'semantic_verified';

      queryInput.disabled = true;
      sendBtn.disabled = true;
      sendBtn.classList.add('opacity-50');

      // User bubble + loading spinner
      var userExchange = document.createElement('div');
      userExchange.className = 'space-y-3';
      userExchange.innerHTML =
        '<div class="flex justify-end">' +
          '<div class="rounded-2xl rounded-tr-sm bg-on-surface text-surface-container-lowest px-4 py-3 max-w-md shadow-sm font-body-md text-body-md">' +
            escapeHtml(query) +
          '</div>' +
        '</div>' +
        '<div class="flex justify-start query-loading-spinner">' +
          '<div class="rounded-2xl rounded-tl-sm bg-surface-container-lowest border border-outline-variant/60 text-on-surface p-4 max-w-xl shadow-sm flex items-center gap-3">' +
            '<div class="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin"></div>' +
            '<span class="text-xs text-on-surface-variant font-code-sm">Querying cache & vector index...</span>' +
          '</div>' +
        '</div>';
      chatLog.appendChild(userExchange);
      queryInput.value = '';
      chatLog.scrollTop = chatLog.scrollHeight;

      sendQuery(query, strategy, 'default').then(function(data) {
        currentMatchedEntryId = data.matched_entry_id;

        var spinner = userExchange.querySelector('.query-loading-spinner');
        if (spinner) spinner.remove();

        userExchange.appendChild(buildResponseBubble(data));
        chatLog.scrollTop = chatLog.scrollHeight;

        updateInspector(data);
        syncHealth();
      }).catch(function(err) {
        var spinner = userExchange.querySelector('.query-loading-spinner');
        if (spinner) spinner.remove();

        var errDiv = document.createElement('div');
        errDiv.className = 'flex justify-start';
        errDiv.innerHTML =
          '<div class="rounded-2xl rounded-tl-sm bg-error-container/40 border border-error/50 text-error p-4 max-w-xl shadow-sm">' +
            '<div class="text-sm font-semibold">Error: ' + escapeHtml(err.message) + '</div>' +
          '</div>';
        userExchange.appendChild(errDiv);
        chatLog.scrollTop = chatLog.scrollHeight;
      }).finally(function() {
        queryInput.disabled = false;
        sendBtn.disabled = false;
        sendBtn.classList.remove('opacity-50');
        queryInput.focus();
      });
    });
  }

  // Reset button
  if (resetSessionBtn) {
    resetSessionBtn.addEventListener('click', function() {
      if (!confirm('Clear all cache entries and query telemetry?')) return;
      adminReset('changeme').then(function() {
        chatLog.innerHTML =
          '<div class="space-y-3"><div class="flex justify-start">' +
            '<div class="rounded-2xl rounded-tl-sm bg-surface-container-lowest border border-outline-variant/60 text-on-surface p-4 max-w-xl shadow-sm">' +
              '<p class="font-body-md text-on-surface">Cache and logs cleared successfully. Ready for new queries.</p>' +
            '</div>' +
          '</div></div>';
        badgeOutcome.textContent = 'READY';
        badgeOutcome.className = 'font-metric-display text-2xl font-bold text-on-surface leading-none tracking-tight';
        inspectorCard.className = 'flex items-center justify-between p-3.5 rounded-lg bg-surface-container-low border border-outline-variant/60';
        inspectorSub.textContent = 'CACHE CLEARED';
        inspectorDetail.textContent = 'Awaiting new queries';
        valSimilarity.textContent = '—';
        valSimilarityBar.style.width = '0%';
        valLookupMs.textContent = '0 ms';
        valTotalMs.textContent = '0 ms';
        valReason.textContent = 'RESET_OK';
        valExplain.textContent = 'Cache cleared by administrator.';
        valMatched.textContent = 'No prior candidate evaluated yet.';
        valMatchedScore.textContent = '—';
        valMatchedId.innerHTML = 'ID: <strong class="text-on-surface">—</strong>';
        currentMatchedEntryId = null;
        syncHealth();
      }).catch(function(e) {
        alert('Reset failed: ' + e.message);
      });
    });
  }

  // Invalidate button
  if (invalidateBtn) {
    invalidateBtn.addEventListener('click', function() {
      if (!currentMatchedEntryId) {
        alert('No matched entry is currently selected to invalidate.');
        return;
      }
      invalidateEntry(currentMatchedEntryId, 'changeme').then(function() {
        var oldText = invalidateBtn.textContent;
        invalidateBtn.textContent = 'Entry #' + currentMatchedEntryId + ' Invalidated!';
        invalidateBtn.classList.add('bg-error/10', 'text-error', 'border-error/40');
        setTimeout(function() {
          invalidateBtn.textContent = oldText;
          invalidateBtn.classList.remove('bg-error/10', 'text-error', 'border-error/40');
        }, 2500);
      }).catch(function(e) {
        alert('Invalidation failed: ' + e.message);
      });
    });
  }
})();


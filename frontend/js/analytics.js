/**
 * CacheIQ — Analytics page logic.
 * PRD §9 DOM IDs: #stat-total, #stat-hits, #stat-misses, #stat-hit-rate,
 *   #stat-avoided, #stat-made, #stat-lat-hit, #stat-lat-miss,
 *   #stat-saved, #reason-list
 */
(function initAnalytics() {
  function loadStats() {
    getStats().then(function(data) {
      document.getElementById('stat-total').textContent = data.total_queries;
      document.getElementById('stat-hits').textContent = data.hits;
      document.getElementById('stat-misses').textContent = data.misses;
      document.getElementById('stat-hit-rate').textContent = (data.hit_rate * 100).toFixed(1) + '%';
      document.getElementById('stat-saved').textContent = '$' + Number(data.est_cost_saved || 0).toFixed(4);
      document.getElementById('stat-avoided').textContent = data.llm_calls_avoided;
      document.getElementById('stat-made').textContent = data.llm_calls_made;
      document.getElementById('stat-lat-hit').textContent = (data.avg_total_ms_hit || 0).toFixed(1) + ' ms';
      document.getElementById('stat-lat-miss').textContent = (data.avg_total_ms_miss || 0).toFixed(1) + ' ms';

      var reasonList = document.getElementById('reason-list');
      reasonList.innerHTML = '';
      var entries = Object.entries(data.by_reason || {});
      if (entries.length === 0) {
        reasonList.innerHTML = '<div class="text-sm text-slate-400 italic">No query traffic recorded yet.</div>';
      } else {
        entries.forEach(function(pair) {
          var code = pair[0], count = pair[1];
          var isHit = code.startsWith('HIT');
          var color = isHit ? 'text-emerald-700 bg-emerald-50 border-emerald-200' : 'text-amber-800 bg-amber-50 border-amber-200';
          var row = document.createElement('div');
          row.className = 'flex items-center justify-between p-3 rounded-lg border border-slate-100 bg-slate-50';
          row.innerHTML =
            '<div class="flex items-center gap-3">' +
              '<span class="px-2 py-0.5 rounded font-code text-xs font-bold border ' + color + '">' + code + '</span>' +
              '<span class="text-xs text-slate-600 font-medium">' + count + ' requests</span>' +
            '</div>' +
            '<span class="font-code text-xs font-semibold">' + (data.total_queries ? ((count / data.total_queries) * 100).toFixed(1) : 0) + '%</span>';
          reasonList.appendChild(row);
        });
      }
    }).catch(function(err) {
      console.error('Failed to load stats:', err);
    });
  }

  document.getElementById('refresh-btn').addEventListener('click', loadStats);
  loadStats();
})();


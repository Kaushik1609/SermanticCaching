/**
 * CacheIQ — Arena page logic.
 * PRD §9 DOM IDs: #arena-run, #arena-body, #arena-winner, #arena-sweep-img
 */
(function initArena() {
  function renderArena(data) {
    var tbody = document.getElementById('arena-body');
    var winnerEl = document.getElementById('arena-winner');
    var runInfoEl = document.getElementById('arena-run-info');

    if (data.run_id) {
      runInfoEl.textContent = 'Run ID: ' + data.run_id + ' • ' + data.dataset_size + ' pairs';
    }
    if (data.winner) {
      winnerEl.textContent = (data.winner.precision || 'Semantic Verified') + ' (Precision)';
    }

    if (!data.rows || data.rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-slate-400">Click "Run Benchmark" to execute evaluation.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    var stratNames = {
      'no_cache': 'A: No Cache',
      'exact_match': 'B: Exact Match',
      'semantic_raw': 'C: Semantic Raw',
      'semantic_verified': 'D: Semantic Verified (CacheIQ)'
    };

    data.rows.forEach(function(r) {
      var isVerified = r.strategy === 'semantic_verified';
      var stratName = stratNames[r.strategy] || r.strategy;

      var row = document.createElement('tr');
      row.className = isVerified ? 'bg-emerald-50/40 font-semibold' : 'hover:bg-slate-50/70';

      var precText = r.precision !== null && r.precision !== undefined ? (r.precision * 100).toFixed(1) + '%' : 'n/a';
      var falseHitText = r.false_hit_rate !== null && r.false_hit_rate !== undefined ? (r.false_hit_rate * 100).toFixed(1) + '%' : '0.0%';
      var hitRateText = (r.hit_rate * 100).toFixed(1) + '%';
      var recallText = (r.recall_same * 100).toFixed(1) + '%';
      var avgLat = r.avg_lookup_ms.toFixed(1) + ' ms';
      var p95Lat = r.p95_lookup_ms.toFixed(1) + ' ms';

      row.innerHTML =
        '<td class="py-3.5 px-4"><div class="flex items-center gap-2">' +
          (isVerified ? '<span class="material-symbols-outlined text-emerald-700 text-[18px]">verified</span>' : '') +
          '<span class="' + (isVerified ? 'text-emerald-900 font-bold' : 'text-slate-800') + '">' + stratName + '</span>' +
        '</div></td>' +
        '<td class="py-3.5 px-4 text-center font-code ' + (r.precision === 1.0 ? 'text-emerald-700 font-bold' : '') + '">' + precText + '</td>' +
        '<td class="py-3.5 px-4 text-center font-code ' + (r.false_hit_rate > 0 ? 'text-rose-600 font-bold' : 'text-slate-600') + '">' + falseHitText + '</td>' +
        '<td class="py-3.5 px-4 text-center font-code">' + hitRateText + '</td>' +
        '<td class="py-3.5 px-4 text-center font-code">' + recallText + '</td>' +
        '<td class="py-3.5 px-4 text-center font-code text-slate-700">' + avgLat + '</td>' +
        '<td class="py-3.5 px-4 text-center font-code text-slate-700">' + p95Lat + '</td>' +
        '<td class="py-3.5 px-4 text-center font-code text-secondary">' + r.llm_calls_avoided + '</td>';
      tbody.appendChild(row);
    });
  }

  // Run Benchmark button
  document.getElementById('arena-run').addEventListener('click', function() {
    var btn = document.getElementById('arena-run');
    btn.disabled = true;
    btn.innerHTML = '<span class="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin"></span> Running benchmark...';
    runArena().then(function(data) {
      renderArena(data);
    }).catch(function(err) {
      alert('Arena run failed: ' + err.message);
    }).finally(function() {
      btn.disabled = false;
      btn.innerHTML = '<span class="material-symbols-outlined text-[18px]">play_arrow</span> Run Benchmark';
    });
  });

  // Load latest on page open
  getArenaLatest().then(function(data) {
    renderArena(data);
  }).catch(function() {});
})();


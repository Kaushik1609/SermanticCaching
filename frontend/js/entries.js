/**
 * CacheIQ — Entries page logic.
 * PRD §9 DOM IDs: #entries-body, #entries-total
 */
(function initEntries() {
  function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function loadEntries() {
    var tbody = document.getElementById('entries-body');
    var totalEl = document.getElementById('entries-total');

    getEntries(100, 0).then(function(data) {
      totalEl.textContent = data.total;

      if (!data.items || data.items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-slate-400 italic">No cache entries stored yet. Send a query in the Chat tab!</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      data.items.forEach(function(item) {
        var isAct = item.status === 'ACTIVE';
        var statusBadge = isAct
          ? '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">ACTIVE</span>'
          : '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">' + item.status + '</span>';

        var row = document.createElement('tr');
        row.className = 'hover:bg-slate-50/70 transition-colors';
        row.innerHTML =
          '<td class="py-3 px-4 font-code text-xs font-bold text-slate-700">#' + item.id + '</td>' +
          '<td class="py-3 px-4 max-w-md font-medium text-slate-900 truncate" title="' + escapeHtml(item.query_text) + '">' + escapeHtml(item.query_text) + '</td>' +
          '<td class="py-3 px-4">' + statusBadge + '</td>' +
          '<td class="py-3 px-4 font-code text-xs">' + (item.hit_count || 0) + '</td>' +
          '<td class="py-3 px-4 font-code text-xs text-slate-500">' + new Date(item.created_at).toLocaleString() + '</td>' +
          '<td class="py-3 px-4 font-code text-xs text-slate-500">' + (item.expires_at ? new Date(item.expires_at).toLocaleString() : '—') + '</td>' +
          '<td class="py-3 px-4 text-right">' +
            (isAct ? '<button class="invalidate-btn px-2.5 py-1 text-xs font-semibold rounded bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200 transition-colors" data-id="' + item.id + '">Invalidate</button>' : '<span class="text-xs text-slate-400">—</span>') +
          '</td>';
        tbody.appendChild(row);
      });

      // Wire invalidation buttons
      document.querySelectorAll('.invalidate-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          var id = e.target.getAttribute('data-id');
          var adminKey = prompt('Enter admin key to invalidate entry #' + id + ':', 'changeme');
          if (!adminKey) return;
          invalidateEntry(id, adminKey).then(function() {
            alert('Entry #' + id + ' invalidated.');
            loadEntries();
          }).catch(function(err) {
            alert('Invalidation failed: ' + err.message);
          });
        });
      });
    }).catch(function(err) {
      tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-rose-500">Failed to load entries: ' + escapeHtml(err.message) + '</td></tr>';
    });
  }

  document.getElementById('refresh-entries-btn').addEventListener('click', loadEntries);
  loadEntries();
})();


'use strict';
// Wires the page to the functions in the other scripts and starts the dashboard.

if (!STALE) {
  document.addEventListener('click', async e => {
    const b = e.target.closest('button');
    if (!b) return;
    try {
      if (b.dataset.view) await navigate(b.dataset.view);
      if (b.dataset.category !== undefined) {
        state.category = b.dataset.category; state.page = 1;
        document.querySelectorAll('[data-category]').forEach(x => x.classList.toggle('selected', x === b));
        await loadNotices();
      }
      if (b.dataset.save) {
        const r = state.items.find(x => x.id === Number(b.dataset.save));
        await api('/api/notices/' + r.id, 'PATCH', {saved: !r.saved}); await refresh();
      }
      if (b.dataset.detail) showDetail(Number(b.dataset.detail));
      if (b.dataset.import) { state.importSource = b.dataset.import; $('#import-file').value = ''; $('#import-file').click(); }
      if (b.dataset.toggle) {
        const s = state.overview.sources.find(s => s.id === Number(b.dataset.toggle));
        await api('/api/sources/' + s.id, 'PATCH', {enabled: !s.enabled}); await loadOverview();
      }
      if (b.dataset.deleteJobword) { await api('/api/jobwords/' + b.dataset.deleteJobword, 'DELETE'); await refresh(); }
      if (b.dataset.deleteWord) { await api('/api/watchwords/' + b.dataset.deleteWord, 'DELETE'); await refresh(); }
      if (b.dataset.stat) {
        for (const id of ['search', 'source', 'from', 'to']) $('#' + id).value = '';
        state.category = '';
        document.querySelectorAll('[data-category]').forEach(x => x.classList.toggle('selected', x.dataset.category === ''));
        await navigate('all');
        state.discovered = b.dataset.stat === 'new' ? 'today' : '';
        $('#status').value = ['open', 'week'].includes(b.dataset.stat) ? b.dataset.stat : '';
        state.page = 1; await loadNotices();
        $('#feed-title').scrollIntoView({behavior: 'smooth', block: 'start'});
      }
    } catch (error) { toast(error.message); }
  });

  const reloadFeed = () => { state.page = 1; loadNotices().catch(e => toast(e.message)); };
  $('#fetch').onclick = async () => {
    try { $('#fetch').disabled = true; await api('/api/fetch', 'POST', {}); await refresh(); }
    catch (e) { toast(e.message); $('#fetch').disabled = false; }
  };
  $('#filters').onsubmit = e => e.preventDefault();
  for (const id of ['status', 'source', 'sort', 'from', 'to', 'disposal-asset', 'disposal-place']) $('#' + id).onchange = reloadFeed;
  $('#search').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(reloadFeed, 300); };
  $('#show-hidden').onclick = () => { $('#status').value = ''; reloadFeed(); };
  $('#clear-filters').onclick = () => {
    for (const id of ['search', 'source', 'from', 'to', 'disposal-asset', 'disposal-place']) $('#' + id).value = '';
    $('#status').value = state.view === 'disposals' ? '' : 'current';
    $('#sort').value = 'latest'; state.discovered = '';
    reloadFeed();
  };
  $('#prev').onclick = () => { state.page--; loadNotices().catch(e => toast(e.message)); };
  $('#next').onclick = () => { state.page++; loadNotices().catch(e => toast(e.message)); };
  $('#close-detail').onclick = () => $('#detail').close();
  wireJobs();
  wireSettings();

  // Alerts open /?view=disposals or /?view=matches; honour it on first load.
  const startView = new URLSearchParams(location.search).get('view');
  if (['matches', 'saved', 'unread', 'jobs', 'disposals'].includes(startView)) navigate(startView).catch(() => {});
  refresh().catch(e => { toast(e.message); $('#cards').innerHTML = '<div class="empty">Could not load your workspace. Check the Python server and reload.</div>'; });
}

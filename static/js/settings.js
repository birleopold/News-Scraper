'use strict';
// Sources & coverage, watchlist, alerts, schedule and saved-page imports.

function renderSources(o) {
  $('#source-list').innerHTML = o.sources.map(s => {
    const health = s.status === 'Needs attention' ? 'bad' : s.status === 'Temporarily unavailable' ? 'temp' : '';
    const importer = s.kind.startsWith('import_') ? `<div class="detail-actions import-actions">
      <button class="secondary" data-import="${s.id}">Import saved page</button>
      <a class="text-button" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Open page to save ↗</a></div>` : '';
    return `<article class="source-card"><div class="source-header"><h3>${esc(s.name)}</h3>
      <button class="toggle" data-toggle="${s.id}" aria-label="${s.enabled ? 'Pause' : 'Enable'} ${esc(s.name)}">${s.enabled ? 'Pause' : 'Enable'}</button></div>
      <a class="url" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a>
      <span class="health ${health}">${s.enabled ? esc(s.status) : 'Paused'} · ${esc(s.group_name)} · ${esc(s.kind)}</span>
      <p>${esc(s.message || 'Ready for the first fetch.')}</p>
      <small>Last checked: ${dateLabel(s.last_checked, true)} · Last successful count: ${s.item_count}</small>${importer}</article>`;
  }).join('');
  $('#run-history').innerHTML = o.runs.map(r => `<div class="history-row"><strong>${esc(r.state)}</strong>
    <span>${dateLabel(r.started_at, true)} ${new Date(r.started_at).toLocaleTimeString('en-GB', {timeZone: 'Africa/Kampala'})}</span>
    <span>${r.added} added · ${r.checked} checked · ${r.failed} need attention</span></div>`).join('') || '<p class="muted">No fetches yet.</p>';
  const broken = o.sources.filter(s => s.enabled && s.status === 'Needs attention').length;
  $('#source-alerts').hidden = !broken;
  $('#source-alerts').textContent = broken;
}

function renderSettings(o) {
  $('#watchwords').innerHTML = o.watchwords.map(w =>
    `<span class="word">${esc(w.term)}<button data-delete-word="${w.id}" aria-label="Remove ${esc(w.term)}">×</button></span>`).join('')
    || '<p class="muted">Add your first keyword to start matching.</p>';
  if (document.activeElement?.closest('#schedule-form') === null) {
    $('#auto-fetch').checked = o.settings.auto_fetch === '1';
    $('#interval').value = o.settings.interval_minutes;
  }
  if (document.activeElement?.closest('#alert-form') === null) {
    $('#alert-mode').value = o.settings.alert_mode || 'disposals';
    const chosen = (o.settings.alert_assets || '').split(',');
    $('#alert-assets').innerHTML = o.asset_names.map(name =>
      `<label class="checkbox"><input type="checkbox" value="${esc(name)}" ${chosen.includes(name) ? 'checked' : ''}> ${esc(name)}</label>`).join('');
    $('#alert-places').value = (o.settings.alert_places || '').split(',').filter(Boolean).join(', ');
    $('#alert-reminders').checked = o.settings.reminders !== '0';
    $('#place-list').innerHTML = o.places.map(p => `<option value="${esc(p)}">`).join('');
  }
  $('#alert-hint').hidden = !(o.watchwords.length === 0 && $('#alert-mode').value === 'matches');
  const last = (o.settings.last_alert || '').split('|');
  $('#last-alert').textContent = last.length > 1
    ? `Last alert: ${dateLabel(last[0], true)} ${new Date(last[0]).toLocaleTimeString('en-GB', {timeZone: 'Africa/Kampala', hour: '2-digit', minute: '2-digit'})} · ${last.slice(1).join('|')}`
    : 'No alerts sent yet.';
}

function wireSettings() {
  $('#add-word').onsubmit = async e => {
    e.preventDefault();
    try { await api('/api/watchwords', 'POST', {term: e.target.term.value}); e.target.reset(); await refresh(); toast('Keyword added.'); }
    catch (error) { toast(error.message); }
  };
  $('#add-source').onsubmit = async e => {
    e.preventDefault();
    try { await api('/api/sources', 'POST', Object.fromEntries(new FormData(e.target))); e.target.reset(); await refresh(); toast('Source added. Fetch latest to check it.'); }
    catch (error) { toast(error.message); }
  };
  $('#schedule-form').onsubmit = async e => {
    e.preventDefault();
    try {
      await api('/api/settings', 'PATCH', {auto_fetch: $('#auto-fetch').checked, interval_minutes: Number($('#interval').value)});
      await loadOverview(); toast('Schedule saved.');
    } catch (error) { toast(error.message); }
  };
  $('#import-file').onchange = async e => {
    const file = e.target.files[0];
    if (!file || !state.importSource) return;
    const form = new FormData();
    form.append('page', file);
    try {
      const r = await fetch(`/api/sources/${state.importSource}/import`, {method: 'POST', headers: {'X-CSRF-Token': csrf}, body: form});
      const payload = await r.json();
      if (!r.ok) throw new Error(payload.error || 'Import failed.');
      toast(`Imported ${payload.found} notices (${payload.added} new).`);
      await refresh();
    } catch (error) { toast(error.message); }
  };
  $('#alert-mode').onchange = () => { $('#alert-hint').hidden = !(state.overview?.watchwords.length === 0 && $('#alert-mode').value === 'matches'); };
  $('#alert-form').onsubmit = async e => {
    e.preventDefault();
    const places = $('#alert-places').value.split(',').map(p => p.trim()).filter(Boolean)
      .map(p => state.overview.places.find(x => x.toLowerCase() === p.toLowerCase()) || p);
    const assets = [...document.querySelectorAll('#alert-assets input:checked')].map(i => i.value);
    try {
      await api('/api/alerts', 'PATCH', {mode: $('#alert-mode').value, assets, places, reminders: $('#alert-reminders').checked});
      await loadOverview(); toast('Alert preferences saved.');
    }
    catch (error) { toast(error.message); }
  };
  $('#test-alert').onclick = async () => {
    const b = $('#test-alert');
    b.disabled = true;
    try { await api('/api/alerts/test', 'POST', {}); toast('Test alert sent. Look at the bottom-right of your screen.'); }
    catch (error) { toast(error.message); }
    finally { b.disabled = false; await loadOverview().catch(() => {}); }
  };
}

'use strict';
// Counts, panels and the fetch banner; refreshed every 30 seconds (3 while fetching).

async function loadOverview() {
  const o = await api('/api/overview');
  state.overview = o;
  for (const [id, key] of [['total', 'total'], ['new', 'new_today'], ['open', 'upcoming'], ['week', 'closing_week']]) $('#stat-' + id).textContent = o.stats[key].toLocaleString();
  $('#saved-count').textContent = o.stats.saved;
  $('#match-count').textContent = o.stats.matches;
  $('#review-count').textContent = o.stats.review;
  $('#today').textContent = new Date(o.today + 'T12:00:00+03:00').toLocaleDateString('en-GB', {weekday: 'short', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Africa/Kampala'});
  const selected = $('#source').value;
  $('#source').innerHTML = '<option value="">All sources</option>' + o.sources.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('#source').value = selected;
  $('#deadlines').innerHTML = o.deadlines.map(r => `<div class="deadline-item">
    <div class="deadline-date">${Number(r.effective_deadline.slice(8, 10))}<small>${new Date(r.effective_deadline + 'T12:00:00').toLocaleDateString('en-GB', {month: 'short'})}</small></div>
    <div><button data-detail="${r.id}">${esc(r.title)}</button><p>${r.days_left === 0 ? 'Due today' : r.days_left + ' days away'}</p></div></div>`).join('')
    || '<p class="muted">Confirmed dates will appear after fetching or reviewing notices.</p>';
  renderDisposalPanel(o);
  renderDisposalFilters(o);
  renderJobWords(o);
  renderSources(o);
  renderSettings(o);
  const latest = o.runs[0];
  const banner = $('#run-banner');
  banner.hidden = !latest;
  if (latest) {
    banner.textContent = latest.state === 'running'
      ? `Checking sources… ${latest.checked} completed · ${latest.added} new records saved.`
      : `Last fetch: ${latest.added} new records · ${latest.checked} sources checked${latest.failed ? ' · ' + latest.failed + ' need attention. See Sources & coverage.' : '.'}`;
  }
  $('#fetch').disabled = latest?.state === 'running';
  $('#fetch').innerHTML = latest?.state === 'running' ? 'Fetching…' : '<span>⟳</span> Fetch latest';
  clearTimeout(pollTimer);
  pollTimer = setTimeout(() => refresh().catch(e => { toast(e.message); pollTimer = setTimeout(() => refresh().catch(() => {}), 30000); }),
    latest?.state === 'running' ? 3000 : 30000);
}

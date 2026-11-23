'use strict';
// The notice feed (Overview, Disposals, Unread, Saved, Keyword matches), navigation and details.

const TITLES = {
  all: ['Stay ahead of the opportunity.', 'Tenders, auctions and business updates. Gathered for you.', 'Overview'],
  disposals: ['Disposals & auctions.', 'Disposal of public assets and other asset sales: eGP disposal notices, newspaper auctions, and notices from public bodies.', 'Disposals & auctions'],
  jobs: ['Jobs & open positions.', 'Ugandan vacancies from job boards, employers and the UN. Search, add your keywords and sort by best match.', 'Jobs & vacancies'],
  saved: ['Your saved opportunities.', 'A shortlist for the business moves that matter.', 'Saved opportunities'],
  unread: ['A fresh perspective.', 'Catch up on notices you haven’t reviewed yet.', 'Unread notices'],
  matches: ['News that fits your interests.', 'Updates matching your personal keyword watchlist.', 'Keyword matches'],
  sources: ['A clear view of your sources.', 'See what is working, what needs attention, and expand your coverage.', 'Sources & coverage'],
  settings: ['Make this desk your own.', 'Choose your interests and how often to check for updates.', 'Watchlist & settings'],
};

function params() {
  const p = new URLSearchParams({view: state.view, category: state.category, page: state.page});
  if (state.discovered) p.set('discovered', state.discovered);
  for (const id of ['search', 'status', 'source', 'sort', 'from', 'to']) if ($('#' + id).value) p.set(id === 'search' ? 'q' : id, $('#' + id).value);
  if (state.view === 'disposals') {
    if ($('#disposal-asset').value) p.set('asset', $('#disposal-asset').value);
    if ($('#disposal-place').value) p.set('place', $('#disposal-place').value);
  }
  return p;
}

function card(r) {
  const discovery = r.source_kind === 'search' ? '<span class="discovery">DISCOVERY</span>' : '';
  const matches = r.matches.length ? `<div class="match-label">◎ Matches: ${r.matches.map(esc).join(', ')}</div>` : '';
  return `<article class="notice-card ${r.read ? 'is-read' : ''}">
    <div class="card-top"><span class="badge ${esc(r.category)}">${esc(label(r.category))}</span><span>${esc(r.publisher || r.source_name)}</span>${discovery}${saveButton(r)}</div>
    <button class="card-title" data-detail="${r.id}">${esc(r.title)}</button><p>${esc(r.excerpt)}</p>${disposalFacts(r)}${matches}
    <div class="card-bottom">${badgeStatus(r)}<span>${r.published_at ? 'Published ' + dateLabel(r.published_at, true) : 'Publication date unknown'}</span></div></article>`;
}

async function loadNotices() {
  const seq = ++state.sequence;
  const data = await api('/api/notices?' + params());
  if (seq !== state.sequence) return;
  state.items = data.items; state.pages = data.pages;
  const current = $('#status').value === 'current' ? 'current ' : '';
  $('#results-label').textContent = `${data.total.toLocaleString()} ${current}${data.total === 1 ? 'update' : 'updates'}${state.category ? ' in ' + label(state.category).toLowerCase() : ''}`;
  $('#show-hidden').hidden = !data.hidden;
  $('#show-hidden').textContent = data.hidden ? `· ${data.hidden.toLocaleString()} closed, older or result ${data.hidden === 1 ? 'record' : 'records'} hidden. Show all` : '';
  const total = state.overview?.stats.total;
  $('#cards').innerHTML = data.items.map(card).join('') || `<div class="empty"><div class="empty-icon">▤</div>
    <h3>${total ? 'No matching updates' : 'Your next opportunity starts here.'}</h3>
    <p>${total ? 'Try another keyword or reset your filters.' : 'Fetch the latest sources to build your personal business brief.'}</p>
    <p>Real source records will appear here. No sample notices are included.</p></div>`;
  $('#page-info').textContent = `Page ${state.page} of ${data.pages}`;
  $('#prev').disabled = state.page <= 1; $('#next').disabled = state.page >= data.pages;
  $('#export').href = '/api/export?' + params();
}

async function refresh() {
  await loadOverview();
  if (state.view === 'jobs') await loadJobs();
  else if (!['sources', 'settings'].includes(state.view)) await loadNotices();
}

async function navigate(view) {
  state.view = view; state.page = 1; state.discovered = ''; state.jobsPage = 1;
  // Saved items and disposals (rare, top priority) show everything; other feeds start on current ones.
  if (!['sources', 'settings', 'jobs'].includes(view)) $('#status').value = ['saved', 'disposals'].includes(view) ? '' : 'current';
  showDisposalFilters(view === 'disposals');
  const [title, description, crumb] = TITLES[view];
  $('#page-title').textContent = title; $('#page-description').textContent = description; $('#breadcrumb').textContent = crumb;
  document.querySelectorAll('.nav').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  $('#notice-view').hidden = ['sources', 'settings', 'jobs'].includes(view);
  $('#jobs-view').hidden = view !== 'jobs';
  $('#sources-view').hidden = view !== 'sources';
  $('#settings-view').hidden = view !== 'settings';
  if (!$('#notice-view').hidden) await loadNotices();
  if (view === 'jobs') await loadJobs();
}

function showDetail(id) {
  const o = state.overview;
  const r = state.items.find(n => n.id === id) || o.deadlines.find(n => n.id === id) || o.latest_disposals.find(n => n.id === id);
  if (!r) return;
  const reviewNote = r.deadline_reviewed ? 'You have manually reviewed the deadline.' : r.deadline_origin === 'extracted' ? 'Automatically extracted date; not yet confirmed.' : '';
  $('#detail-content').innerHTML = `<h2>${esc(r.title)}</h2>
    <div class="card-top"><span class="badge ${esc(r.category)}">${esc(label(r.category))}</span>${esc(r.publisher)}</div><p>${esc(r.excerpt)}</p>
    <div class="detail-meta"><div><small>Deadline status</small>${badgeStatus(r)}</div><div><small>Published</small>${dateLabel(r.published_at, true)}</div>
      <div><small>First discovered</small>${dateLabel(r.first_seen, true)}</div><div><small>Last seen</small>${dateLabel(r.last_seen, true)}</div>
      <div><small>Source</small>${esc(r.source_name)}</div><div><small>Reference</small>${esc(r.reference || 'Not supplied')}</div></div>
    <p class="fine-print">${esc(r.deadline_evidence || 'No explicit deadline was extracted. Review the original notice.')} ${reviewNote}</p>
    ${r.category === 'Auction' ? disposalDetail(r) : ''}
    <div class="detail-actions"><a href="${esc(r.url)}" class="primary" target="_blank" rel="noopener noreferrer">${r.source_kind === 'search' ? 'Open discovery link' : 'Read original notice'}</a>
      <button class="secondary" id="mark-read">${r.read ? 'Mark unread' : 'Mark as read'}</button></div>
    <form class="detail-form" id="annotation-form">
      <label>Reviewed deadline (confirm on the original notice)<input type="date" id="reviewed-deadline" value="${esc(r.effective_deadline || '')}"></label>
      <label>Your notes<textarea id="personal-notes" maxlength="5000" placeholder="Requirements, contacts, next steps…">${esc(r.notes)}</textarea></label>
      <div class="detail-actions"><button class="primary">Save notes & reviewed deadline</button><button type="button" class="secondary" id="save-notes">Save notes only</button>
        <button type="button" class="text-button" id="reset-date">Use source deadline</button></div>
      <p class="fine-print">A reviewed future date counts as upcoming. Saving a blank deadline keeps the notice in Needs review.</p></form>`;
  $('#detail').showModal();
  if (r.category === 'Auction') loadHistory(id);
  $('#mark-read').onclick = async () => {
    try { await api('/api/notices/' + id, 'PATCH', {read: !r.read}); $('#detail').close(); await refresh(); } catch (e) { toast(e.message); }
  };
  async function save(data) {
    try { await api('/api/notices/' + id, 'PATCH', data); $('#detail').close(); toast('Your changes are saved.'); await refresh(); } catch (e) { toast(e.message); }
  }
  $('#annotation-form').onsubmit = e => { e.preventDefault(); save({notes: $('#personal-notes').value, user_deadline: $('#reviewed-deadline').value}); };
  $('#save-notes').onclick = () => save({notes: $('#personal-notes').value});
  $('#reset-date').onclick = () => save({reset_deadline: true});
}

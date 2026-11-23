'use strict';
// Jobs & vacancies: search, job keywords and ranking by best match.

function renderJobWords(o) {
  $('#job-words').innerHTML = o.job_words.map(w =>
    `<span class="word">${esc(w.term)}<button data-delete-jobword="${w.id}" aria-label="Remove ${esc(w.term)}">×</button></span>`).join('')
    || '<p class="muted">No job keywords yet.</p>';
  const chosen = $('#jobs-source').value;
  $('#jobs-source').innerHTML = '<option value="">All job sources</option>' +
    o.sources.filter(s => s.group_name === 'Jobs').map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join('');
  $('#jobs-source').value = chosen;
  $('#job-count').textContent = o.stats.jobs_open.toLocaleString();
}

function jobParams() {
  const p = new URLSearchParams({view: 'jobs', page: state.jobsPage, sort: $('#jobs-sort').value, status: $('#jobs-status').value});
  if ($('#jobs-search').value.trim()) p.set('q', $('#jobs-search').value.trim());
  if ($('#jobs-source').value) p.set('source', $('#jobs-source').value);
  if ($('#jobs-mine').checked) p.set('mine', '1');
  return p;
}

function jobCard(r) {
  const who = [r.organization, r.publisher || r.source_name].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(' · ');
  const closes = r.effective_deadline ? ` · ${r.status === 'Closed' ? 'Closed' : 'Closes'} ${dateLabel(r.effective_deadline, true)}` : '';
  const cls = ['Closed', 'Older post', 'No longer listed'].includes(r.status) ? 'expired' : '';
  const matches = r.job_matches.length ? `<div class="match-label">◎ Matches: ${r.job_matches.map(esc).join(', ')}</div>` : '';
  return `<article class="notice-card job-card ${r.read ? 'is-read' : ''}">
    <div class="card-top"><span class="badge Job">Job</span><span>${esc(who)}</span>${saveButton(r, 'job')}</div>
    <button class="card-title" data-detail="${r.id}">${esc(r.title)}</button><p>${esc(r.excerpt)}</p>${matches}
    <div class="card-bottom"><span class="status ${cls}">${esc(r.status)}${closes}</span>
      <span>${r.published_at ? 'Posted ' + dateLabel(r.published_at, true) : 'Found ' + dateLabel(r.first_seen, true)}</span></div></article>`;
}

async function loadJobs() {
  const seq = ++state.sequence;
  const data = await api('/api/notices?' + jobParams());
  if (seq !== state.sequence) return;
  state.items = data.items;
  const words = state.overview?.job_words.length || 0;
  const open = $('#jobs-status').value === 'current' ? 'open ' : '';
  const hidden = data.hidden ? ` · ${data.hidden.toLocaleString()} closed or older hidden` : '';
  const hint = $('#jobs-sort').value === 'match' && !words ? ' · add job keywords to rank by best match' : '';
  $('#jobs-label').textContent = `${data.total.toLocaleString()} ${open}${data.total === 1 ? 'job' : 'jobs'}${hidden}${hint}`;
  $('#job-cards').innerHTML = data.items.map(jobCard).join('') || `<div class="empty"><div class="empty-icon">✎</div><h3>No matching jobs</h3>
    <p>${state.overview?.stats.jobs_open ? 'Try another search, untick “Only jobs matching my keywords”, or include closed jobs.' : 'Fetch the latest sources to load job posts.'}</p></div>`;
  $('#jobs-page-info').textContent = `Page ${state.jobsPage} of ${data.pages}`;
  $('#jobs-prev').disabled = state.jobsPage <= 1; $('#jobs-next').disabled = state.jobsPage >= data.pages;
  $('#jobs-export').href = '/api/export?' + jobParams();
}

function wireJobs() {
  const reload = () => { state.jobsPage = 1; loadJobs().catch(e => toast(e.message)); };
  for (const id of ['jobs-sort', 'jobs-status', 'jobs-source', 'jobs-mine']) $('#' + id).onchange = reload;
  $('#jobs-filters').onsubmit = e => e.preventDefault();
  $('#jobs-search').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(reload, 300); };
  $('#jobs-prev').onclick = () => { state.jobsPage--; loadJobs().catch(e => toast(e.message)); };
  $('#jobs-next').onclick = () => { state.jobsPage++; loadJobs().catch(e => toast(e.message)); };
  $('#add-job-word').onsubmit = async e => {
    e.preventDefault();
    try { await api('/api/jobwords', 'POST', {term: e.target.term.value}); e.target.reset(); await refresh(); toast('Job keyword added.'); }
    catch (error) { toast(error.message); }
  };
}

'use strict';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {view:'all', category:'', discovered:'', page:1, pages:1, items:[], overview:null, sequence:0};
const csrf = $('meta[name="csrf-token"]').content;
let toastTimer, pollTimer, searchTimer;
function toast(message) { $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,4500); }
async function api(path, method='GET', data) {
  const r=await fetch(path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});
  const payload=await r.json(); if(!r.ok) throw new Error(payload.error || 'The request could not be completed.'); return payload;
}
function dateLabel(value,full=false) {
  if(!value) return 'Not supplied';
  const d=new Date(value.length===10?value+'T12:00:00+03:00':value);
  return Number.isNaN(d.getTime())?'Not supplied':d.toLocaleDateString('en-GB',{day:'numeric',month:'short',...(full?{year:'numeric'}:{}),timeZone:'Africa/Kampala'});
}
function params() {
  const p=new URLSearchParams({view:state.view,category:state.category,page:state.page});
  if(state.discovered)p.set('discovered',state.discovered);
  for(const id of ['search','status','source','sort','from','to']) if($('#'+id).value) p.set(id==='search'?'q':id,$('#'+id).value);
  return p;
}
function badgeStatus(r) { return `<span class="status ${r.status==='Needs review'?'review':['Expired','Result'].includes(r.status)?'expired':''}">${esc(r.status)}${r.effective_deadline?' · '+dateLabel(r.effective_deadline,true):''}</span>`; }
function card(r) {
  return `<article class="notice-card ${r.read?'is-read':''}"><div class="card-top"><span class="badge ${esc(r.category)}">${esc(r.category)}</span><span>${esc(r.publisher || r.source_name)}</span>${r.source_kind==='search'?'<span class="discovery">DISCOVERY</span>':''}<button class="save ${r.saved?'saved':''}" data-save="${r.id}" aria-label="${r.saved?'Unsave':'Save'} notice" aria-pressed="${!!r.saved}">${r.saved?'★':'☆'}</button></div><button class="card-title" data-detail="${r.id}">${esc(r.title)}</button><p>${esc(r.excerpt)}</p>${r.matches.length?`<div class="match-label">◎ Matches: ${r.matches.map(esc).join(', ')}</div>`:''}<div class="card-bottom">${badgeStatus(r)}<span>${r.published_at?'Published '+dateLabel(r.published_at,true):'Publication date unknown'}</span></div></article>`;
}
async function loadNotices() {
  const seq=++state.sequence; const data=await api('/api/notices?'+params()); if(seq!==state.sequence)return;
  state.items=data.items; state.pages=data.pages;
  $('#results-label').textContent=`${data.total.toLocaleString()} ${$('#status').value==='current'?'current ':''}${data.total===1?'update':'updates'}${state.category?' in '+state.category.toLowerCase():''}`;
  $('#show-hidden').hidden=!data.hidden;
  $('#show-hidden').textContent=data.hidden?`· ${data.hidden.toLocaleString()} closed, older or result ${data.hidden===1?'record':'records'} hidden. Show all`:'';
  $('#cards').innerHTML=data.items.map(card).join('') || `<div class="empty"><div class="empty-icon">▤</div><h3>${state.overview?.stats.total?'No matching updates':'Your next opportunity starts here.'}</h3><p>${state.overview?.stats.total?'Try another keyword or reset your filters.':'Fetch the latest sources to build your personal business brief.'}</p><p>Real source records will appear here. No sample notices are included.</p></div>`;
  $('#page-info').textContent=`Page ${state.page} of ${data.pages}`;
  $('#prev').disabled=state.page<=1; $('#next').disabled=state.page>=data.pages;
  $('#export').href='/api/export?'+params();
}
function renderSources(o) {
  $('#source-list').innerHTML=o.sources.map(s=>`<article class="source-card"><div class="source-header"><h3>${esc(s.name)}</h3><button class="toggle" data-toggle="${s.id}" aria-label="${s.enabled?'Pause':'Enable'} ${esc(s.name)}">${s.enabled?'Pause':'Enable'}</button></div><a class="url" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a><span class="health ${s.status==='Needs attention'?'bad':''}">${s.enabled?esc(s.status):'Paused'} · ${esc(s.group_name)} · ${esc(s.kind)}</span><p>${esc(s.message || 'Ready for the first fetch.')}</p><small>Last checked: ${dateLabel(s.last_checked,true)} · Last successful count: ${s.item_count}</small></article>`).join('');
  $('#run-history').innerHTML=o.runs.map(r=>`<div class="history-row"><strong>${esc(r.state)}</strong><span>${dateLabel(r.started_at,true)} ${new Date(r.started_at).toLocaleTimeString('en-GB',{timeZone:'Africa/Kampala'})}</span><span>${r.added} added · ${r.checked} checked · ${r.failed} need attention</span></div>`).join('') || '<p class="muted">No fetches yet.</p>';
}
function renderWords(o) {
  $('#watchwords').innerHTML=o.watchwords.map(w=>`<span class="word">${esc(w.term)}<button data-delete-word="${w.id}" aria-label="Remove ${esc(w.term)}">×</button></span>`).join('') || '<p class="muted">Add your first keyword to start matching.</p>';
}
async function loadOverview() {
  const o=await api('/api/overview');state.overview=o;
  for(const [id,key] of [['total','total'],['new','new_today'],['open','upcoming'],['week','closing_week']]) $('#stat-'+id).textContent=o.stats[key].toLocaleString();
  $('#saved-count').textContent=o.stats.saved;$('#match-count').textContent=o.stats.matches;$('#review-count').textContent=o.stats.review;
  $('#today').textContent=new Date(o.today+'T12:00:00+03:00').toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'long',year:'numeric',timeZone:'Africa/Kampala'});
  const selected=$('#source').value;
  $('#source').innerHTML='<option value="">All sources</option>'+o.sources.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');$('#source').value=selected;
  $('#deadlines').innerHTML=o.deadlines.map(r=>`<div class="deadline-item"><div class="deadline-date">${Number(r.effective_deadline.slice(8,10))}<small>${new Date(r.effective_deadline+'T12:00:00').toLocaleDateString('en-GB',{month:'short'})}</small></div><div><button data-detail="${r.id}">${esc(r.title)}</button><p>${r.days_left===0?'Due today':r.days_left+' days away'}</p></div></div>`).join('') || '<p class="muted">Confirmed dates will appear after fetching or reviewing notices.</p>';
  renderSources(o);renderWords(o);
  if(document.activeElement?.closest('#schedule-form')===null){$('#auto-fetch').checked=o.settings.auto_fetch==='1';$('#interval').value=o.settings.interval_minutes;}
  const latest=o.runs[0];const banner=$('#run-banner');
  banner.hidden=!latest;
  if(latest){banner.textContent=latest.state==='running'?`Checking sources… ${latest.checked} completed · ${latest.added} new records saved.`:`Last fetch: ${latest.added} new records · ${latest.checked} sources checked${latest.failed?' · '+latest.failed+' need attention. See Sources & coverage.':'.'}`;}
  $('#fetch').disabled=latest?.state==='running';$('#fetch').innerHTML=latest?.state==='running'?'Fetching…':'<span>⟳</span> Fetch latest';
  clearTimeout(pollTimer);pollTimer=setTimeout(()=>refresh().catch(e=>{toast(e.message);pollTimer=setTimeout(()=>refresh().catch(()=>{}),30000)}),latest?.state==='running'?3000:30000);
}
async function refresh(){await loadOverview();if(!['sources','settings'].includes(state.view))await loadNotices();}
async function navigate(view){
  state.view=view;state.page=1;state.discovered='';
  // Saved items stay visible after they close; other feeds start on current opportunities.
  if(!['sources','settings'].includes(view))$('#status').value=view==='saved'?'':'current';
  const titles={all:['Stay ahead of the opportunity.','Tenders, auctions and business updates. Gathered for you.','Overview'],saved:['Your saved opportunities.','A shortlist for the business moves that matter.','Saved opportunities'],unread:['A fresh perspective.','Catch up on notices you haven’t reviewed yet.','Unread notices'],matches:['News that fits your interests.','Updates matching your personal keyword watchlist.','Keyword matches'],sources:['A clear view of your sources.','See what is working, what needs attention, and expand your coverage.','Sources & coverage'],settings:['Make this desk your own.','Choose your interests and how often to check for updates.','Watchlist & settings']};
  const t=titles[view];$('#page-title').textContent=t[0];$('#page-description').textContent=t[1];$('#breadcrumb').textContent=t[2];
  document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $('#notice-view').hidden=['sources','settings'].includes(view);$('#sources-view').hidden=view!=='sources';$('#settings-view').hidden=view!=='settings';
  if(!$('#notice-view').hidden)await loadNotices();
}
function showDetail(id){
  const r=state.items.find(n=>n.id===id)||state.overview.deadlines.find(n=>n.id===id);if(!r)return;
  $('#detail-content').innerHTML=`<h2>${esc(r.title)}</h2><div class="card-top"><span class="badge ${esc(r.category)}">${esc(r.category)}</span>${esc(r.publisher)}</div><p>${esc(r.excerpt)}</p><div class="detail-meta"><div><small>Deadline status</small>${badgeStatus(r)}</div><div><small>Published</small>${dateLabel(r.published_at,true)}</div><div><small>First discovered</small>${dateLabel(r.first_seen,true)}</div><div><small>Last seen</small>${dateLabel(r.last_seen,true)}</div><div><small>Source</small>${esc(r.source_name)}</div><div><small>Reference</small>${esc(r.reference || 'Not supplied')}</div></div><p class="fine-print">${esc(r.deadline_evidence || 'No explicit deadline was extracted. Review the original notice.')} ${r.deadline_reviewed?'You have manually reviewed the deadline.':r.deadline_origin==='extracted'?'Automatically extracted date; not yet confirmed.':''}</p><div class="detail-actions"><a href="${esc(r.url)}" class="primary" target="_blank" rel="noopener noreferrer">${r.source_kind==='search'?'Open discovery link':'Read original notice'}</a><button class="secondary" id="mark-read">${r.read?'Mark unread':'Mark as read'}</button></div><form class="detail-form" id="annotation-form"><label>Reviewed deadline (confirm on the original notice)<input type="date" id="reviewed-deadline" value="${esc(r.effective_deadline || '')}"></label><label>Your notes<textarea id="personal-notes" maxlength="5000" placeholder="Requirements, contacts, next steps…">${esc(r.notes)}</textarea></label><div class="detail-actions"><button class="primary">Save notes & reviewed deadline</button><button type="button" class="secondary" id="save-notes">Save notes only</button><button type="button" class="text-button" id="reset-date">Use source deadline</button></div><p class="fine-print">A reviewed future date counts as upcoming. Saving a blank deadline keeps the notice in Needs review.</p></form>`;
  $('#detail').showModal();
  $('#mark-read').onclick=async()=>{try{await api('/api/notices/'+id,'PATCH',{read:!r.read});$('#detail').close();await refresh();}catch(e){toast(e.message)}};
  async function save(data){try{await api('/api/notices/'+id,'PATCH',data);$('#detail').close();toast('Your changes are saved.');await refresh();}catch(e){toast(e.message)}}
  $('#annotation-form').onsubmit=e=>{e.preventDefault();save({notes:$('#personal-notes').value,user_deadline:$('#reviewed-deadline').value})};
  $('#save-notes').onclick=()=>save({notes:$('#personal-notes').value});$('#reset-date').onclick=()=>save({reset_deadline:true});
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  try{
    if(b.dataset.view)await navigate(b.dataset.view);
    if(b.dataset.category!==undefined){state.category=b.dataset.category;state.page=1;document.querySelectorAll('[data-category]').forEach(x=>x.classList.toggle('selected',x===b));await loadNotices();}
    if(b.dataset.save){const r=state.items.find(x=>x.id===Number(b.dataset.save));await api('/api/notices/'+r.id,'PATCH',{saved:!r.saved});await refresh();}
    if(b.dataset.detail)showDetail(Number(b.dataset.detail));
    if(b.dataset.toggle){const s=state.overview.sources.find(s=>s.id===Number(b.dataset.toggle));await api('/api/sources/'+s.id,'PATCH',{enabled:!s.enabled});await loadOverview();}
    if(b.dataset.deleteWord){await api('/api/watchwords/'+b.dataset.deleteWord,'DELETE');await refresh();}
    if(b.dataset.stat){for(const id of ['search','source','from','to'])$('#'+id).value='';state.category='';document.querySelectorAll('[data-category]').forEach(x=>x.classList.toggle('selected',x.dataset.category===''));await navigate('all');state.discovered=b.dataset.stat==='new'?'today':'';$('#status').value=['open','week'].includes(b.dataset.stat)?b.dataset.stat:'';state.page=1;await loadNotices();$('#feed-title').scrollIntoView({behavior:'smooth',block:'start'});}
  }catch(error){toast(error.message)}
});
$('#fetch').onclick=async()=>{try{$('#fetch').disabled=true;await api('/api/fetch','POST',{});await refresh();}catch(e){toast(e.message);$('#fetch').disabled=false}};
$('#filters').onsubmit=e=>e.preventDefault();
for(const id of ['status','source','sort','from','to'])$('#'+id).onchange=()=>{state.page=1;loadNotices().catch(e=>toast(e.message))};
$('#search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.page=1;loadNotices().catch(e=>toast(e.message))},300)};
$('#show-hidden').onclick=()=>{$('#status').value='';state.page=1;loadNotices().catch(e=>toast(e.message))};
$('#clear-filters').onclick=()=>{for(const id of ['search','source','from','to'])$('#'+id).value='';$('#status').value='current';$('#sort').value='latest';state.page=1;state.discovered='';loadNotices().catch(e=>toast(e.message))};
$('#prev').onclick=()=>{state.page--;loadNotices().catch(e=>toast(e.message))};$('#next').onclick=()=>{state.page++;loadNotices().catch(e=>toast(e.message))};
$('#close-detail').onclick=()=>$('#detail').close();
$('#add-word').onsubmit=async e=>{e.preventDefault();try{await api('/api/watchwords','POST',{term:e.target.term.value});e.target.reset();await refresh();toast('Keyword added.');}catch(error){toast(error.message)}};
$('#add-source').onsubmit=async e=>{e.preventDefault();try{await api('/api/sources','POST',Object.fromEntries(new FormData(e.target)));e.target.reset();await refresh();toast('Source added. Fetch latest to check it.');}catch(error){toast(error.message)}};
$('#schedule-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings','PATCH',{auto_fetch:$('#auto-fetch').checked,interval_minutes:Number($('#interval').value)});await loadOverview();toast('Schedule saved.');}catch(error){toast(error.message)}};
refresh().catch(e=>{toast(e.message);$('#cards').innerHTML='<div class="empty">Could not load your workspace. Check the Python server and reload.</div>'});

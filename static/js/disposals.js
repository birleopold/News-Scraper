'use strict';
// Disposals & auctions: facts read from advert PDFs, filters, and past results.

function disposalFacts(r) {
  if (r.category !== 'Auction') return '';
  const f = r.facts || {};
  const bits = [];
  if (r.pipeline) bits.push('● ' + STAGES[r.pipeline] + (r.my_bid ? ` (your bid ${ugx(r.my_bid)})` : ''));
  if (r.assets?.length) bits.push(r.assets.join(', '));
  if (f.lots) bits.push(`${f.lots} lots`);
  if (r.places?.length) bits.push(r.places.slice(0, 3).join(' / '));
  if (f.viewing) bits.push('viewing ' + dateLabel(f.viewing, true));
  if (f.auction_date) bits.push('auction ' + dateLabel(f.auction_date, true));
  if (f.bid_security) bits.push('bid security ' + ugx(f.bid_security));
  if (f.ocr) bits.push('read from a scanned advert');
  if (f.scanned) bits.push('scanned advert: open it to read');
  if (r.also_at?.length) bits.push(`also on ${r.also_at.length} other source${r.also_at.length > 1 ? 's' : ''}`);
  return bits.length ? `<div class="facts-line">⚖ ${esc(bits.join(' · '))}</div>` : '';
}

function disposalDetail(r) {
  const f = r.facts || {};
  const rows = [
    ['Assets', r.assets?.join(', ')], ['Places', r.places?.join(', ')], ['Lots', f.lots],
    ['Viewing / inspection', f.viewing && dateLabel(f.viewing, true)], ['Auction date', f.auction_date && dateLabel(f.auction_date, true)],
    ['Bid security', f.bid_security && ugx(f.bid_security)],
  ].filter(([, v]) => v);
  const facts = rows.length
    ? `<div class="detail-meta">${rows.map(([k, v]) => `<div><small>${k}</small>${esc(v)}</div>`).join('')}</div>`
    : '';
  const note = f.ocr ? 'Facts above were read automatically from a scanned advert (text recognition can misread). Confirm them in the advert.'
    : f.scanned ? 'The advert PDF is a scanned image, so its details could not be read automatically. Open it to read the assets and dates.'
    : f.source_pdf ? 'Facts above were read automatically from the advert PDF. Confirm them in the advert before acting.' : '';
  const also = r.also_at?.length
    ? `<p class="fine-print">Also listed at: ${r.also_at.map(a => `<a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">${esc(a.source)}</a>`).join(', ')}</p>` : '';
  const pdf = f.source_pdf && f.source_pdf !== r.url
    ? ` <a href="${esc(f.source_pdf)}" target="_blank" rel="noopener noreferrer">Open the advert PDF ↗</a>` : '';
  return `<h3 class="detail-heading">What is being sold</h3>${facts}<p class="fine-print">${esc(note)}${pdf}</p>${also}
    <h3 class="detail-heading">Past disposals &amp; results</h3><div id="disposal-history" class="history-list"><p class="muted">Looking for similar past disposals…</p></div>`;
}

async function loadHistory(id) {
  const box = $('#disposal-history');
  try {
    const {items} = await api(`/api/notices/${id}/history`);
    if (!box.isConnected) return;
    box.innerHTML = items.length ? items.map(h => {
      const money = h.amounts?.length ? (h.amounts.length > 1 ? `${ugx(h.amounts[0])} – ${ugx(h.amounts[h.amounts.length - 1])}` : ugx(h.amounts[0])) : '';
      const mine = [h.pipeline && STAGES[h.pipeline], h.my_bid && 'your bid ' + ugx(h.my_bid), h.outcome_amount && 'winning ' + ugx(h.outcome_amount)].filter(Boolean).join(', ');
      const meta = [h.organization, dateLabel(h.date, true), h.status, mine && 'YOU: ' + mine, money && 'amounts in advert: ' + money,
        h.bid_security && 'bid security ' + ugx(h.bid_security)].filter(Boolean).join(' · ');
      return `<div class="history-item"><a href="${esc(h.url)}" target="_blank" rel="noopener noreferrer">${esc(h.title)}</a><p>${esc(meta)}</p></div>`;
    }).join('') + '<p class="fine-print">Amounts are as printed in those adverts (reserve prices, bid security or results), not confirmed sale prices.</p>'
      : '<p class="muted">No earlier disposals of the same kind of asset yet. This list grows as the app collects more.</p>';
  } catch (e) {
    box.innerHTML = '<p class="muted">Past results could not be loaded.</p>';
  }
}

function renderDisposalFilters(o) {
  for (const [id, key, all] of [['disposal-asset', 'assets', 'All asset types'], ['disposal-place', 'places', 'All places']]) {
    const select = $('#' + id);
    const chosen = select.value;
    select.innerHTML = `<option value="">${all}</option>` +
      o.disposal_facets[key].map(x => `<option value="${esc(x.name)}">${esc(x.name)} (${x.count})</option>`).join('');
    select.value = chosen;
  }
}

function renderDisposalPanel(o) {
  $('#disposal-count').textContent = o.stats.disposals.toLocaleString();
  $('#latest-disposals').innerHTML = o.latest_disposals.map(r => {
    const when = r.effective_deadline ? ' · ' + (r.status === 'Needs review' ? 'date to confirm ' : 'closes ') + dateLabel(r.effective_deadline, true) : '';
    return `<div class="disposal-item"><button data-detail="${r.id}">${esc(r.title)}</button><p>${esc(r.organization || r.publisher || r.source_name)}${when}</p></div>`;
  }).join('') || '<p class="muted">No current disposals right now. New ones will appear here and trigger an alert.</p>';
}

function showDisposalFilters(show) {
  for (const id of ['disposal-asset', 'disposal-place', 'disposal-pipeline']) {
    $('#' + id).hidden = !show;
    if (!show) $('#' + id).value = '';
  }
}

function trackerForm(r) {
  if (r.category === 'Job') return '';
  const options = Object.entries({'': 'Not tracking', ...STAGES}).map(([v, t]) => `<option value="${v}" ${r.pipeline === v ? 'selected' : ''}>${t}</option>`).join('');
  const f = r.facts || {};
  const hasDates = f.viewing || f.auction_date || r.effective_deadline;
  return `<h3 class="detail-heading">Your tracker</h3><form class="tracker-form" id="tracker-form">
    <label>Stage<select id="tracker-stage">${options}</select></label>
    <label>Your bid (UGX)<input id="tracker-bid" inputmode="numeric" placeholder="e.g. 12,500,000" value="${r.my_bid ?? ''}"></label>
    <label>Winning amount (UGX)<input id="tracker-outcome" inputmode="numeric" placeholder="when known" value="${r.outcome_amount ?? ''}"></label>
    <button class="secondary">Save tracker</button></form>
    ${hasDates ? `<p class="fine-print"><a href="/api/notices/${r.id}/calendar.ics">⇩ Add its dates to your calendar (.ics)</a></p>` : ''}`;
}

function wireTracker(id) {
  const form = $('#tracker-form');
  if (!form) return;
  form.onsubmit = async e => {
    e.preventDefault();
    try {
      await api('/api/notices/' + id, 'PATCH', {pipeline: $('#tracker-stage').value, my_bid: $('#tracker-bid').value.trim() || null,
        outcome_amount: $('#tracker-outcome').value.trim() || null});
      toast('Tracker saved.'); await refresh();
    } catch (error) { toast(error.message); }
  };
}

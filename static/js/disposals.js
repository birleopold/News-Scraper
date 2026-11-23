'use strict';
// Disposals & auctions: facts read from advert PDFs, filters, and past results.

function disposalFacts(r) {
  if (r.category !== 'Auction') return '';
  const f = r.facts || {};
  const bits = [];
  if (r.assets?.length) bits.push(r.assets.join(', '));
  if (f.lots) bits.push(`${f.lots} lots`);
  if (r.places?.length) bits.push(r.places.slice(0, 3).join(' / '));
  if (f.viewing) bits.push('viewing ' + dateLabel(f.viewing, true));
  if (f.auction_date) bits.push('auction ' + dateLabel(f.auction_date, true));
  if (f.bid_security) bits.push('bid security ' + ugx(f.bid_security));
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
  const note = f.scanned ? 'The advert PDF is a scanned image, so its details could not be read automatically. Open it to read the assets and dates.'
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
      const meta = [h.organization, dateLabel(h.date, true), h.status, money && 'amounts in advert: ' + money,
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
  $('#disposal-asset').hidden = !show;
  $('#disposal-place').hidden = !show;
  if (!show) { $('#disposal-asset').value = ''; $('#disposal-place').value = ''; }
}

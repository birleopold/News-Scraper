'use strict';
// Shared helpers and state. Loaded first; the other scripts only define functions,
// and main.js wires everything to the page.
const $ = s => document.querySelector(s);
const LABELS = {Auction: 'Disposal / auction'};
const label = c => LABELS[c] || c;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const ugx = n => 'UGX ' + Number(n).toLocaleString('en-GB');
const state = {view: 'all', category: '', discovered: '', page: 1, pages: 1, items: [], overview: null, sequence: 0, jobsPage: 1};
let toastTimer, pollTimer, searchTimer;

// If the app was updated while its server kept running, the page and these scripts can
// disagree. Say so plainly instead of failing on missing elements.
const REQUIRED = ['cards', 'status', 'disposal-count', 'latest-disposals', 'disposal-asset', 'disposal-place', 'jobs-view', 'job-cards',
  'job-words', 'import-file', 'show-hidden', 'source-alerts', 'alert-form', 'alert-mode', 'alert-hint', 'last-alert', 'test-alert'];
const STALE = REQUIRED.some(id => !document.getElementById(id));
if (STALE) {
  const note = document.createElement('div');
  note.setAttribute('role', 'alert');
  note.innerHTML = '<strong>Uganda Business Watch was updated while it was running.</strong> Close the app’s window (or press Ctrl+C where it runs), start it again with <code>run.py</code> or “Start Business Watch”, then reload this page.';
  // Styles are set through the DOM because the page's security policy blocks inline style attributes.
  Object.assign(note.style, {padding: '16px 20px', background: '#fbeed5', color: '#5c3d0b', borderBottom: '1px solid #e8cf9f',
    font: '15px/1.5 Segoe UI,Arial,sans-serif', position: 'fixed', top: '0', left: '0', right: '0', zIndex: '50', boxShadow: '0 4px 16px #0002'});
  document.body.prepend(note);
}
const csrf = $('meta[name="csrf-token"]')?.content;

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('#toast').hidden = true, 4500);
}

async function api(path, method = 'GET', data) {
  const r = await fetch(path, {method, headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    body: data === undefined ? undefined : JSON.stringify(data)});
  const payload = await r.json();
  if (!r.ok) throw new Error(payload.error || 'The request could not be completed.');
  return payload;
}

function dateLabel(value, full = false) {
  if (!value) return 'Not supplied';
  const d = new Date(value.length === 10 ? value + 'T12:00:00+03:00' : value);
  return Number.isNaN(d.getTime()) ? 'Not supplied'
    : d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', ...(full ? {year: 'numeric'} : {}), timeZone: 'Africa/Kampala'});
}

function badgeStatus(r) {
  const cls = r.status === 'Needs review' ? 'review' : ['Expired', 'Result'].includes(r.status) ? 'expired' : '';
  return `<span class="status ${cls}">${esc(r.status)}${r.effective_deadline ? ' · ' + dateLabel(r.effective_deadline, true) : ''}</span>`;
}

function saveButton(r, noun = 'notice') {
  return `<button class="save ${r.saved ? 'saved' : ''}" data-save="${r.id}" aria-label="${r.saved ? 'Unsave' : 'Save'} ${noun}" aria-pressed="${!!r.saved}">${r.saved ? '★' : '☆'}</button>`;
}

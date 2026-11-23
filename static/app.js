'use strict';
// The dashboard now lives in static/js/*.js. Only a copy of the app started before that change
// still loads this file; tell its user to restart instead of showing a broken page.
(() => {
  const note = document.createElement('div');
  note.setAttribute('role', 'alert');
  note.innerHTML = '<strong>Uganda Business Watch was updated while it was running.</strong> Close the app’s window (or press Ctrl+C where it runs), start it again with <code>run.py</code> or “Start Business Watch”, then reload this page.';
  Object.assign(note.style, {padding: '16px 20px', background: '#fbeed5', color: '#5c3d0b', borderBottom: '1px solid #e8cf9f',
    font: '15px/1.5 Segoe UI,Arial,sans-serif', position: 'fixed', top: '0', left: '0', right: '0', zIndex: '50'});
  document.body.prepend(note);
})();

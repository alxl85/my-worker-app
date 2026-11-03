from workers import WorkerEntrypoint, Response
from pyodide.ffi import to_js
import json
import re
from datetime import date as _date, timedelta
from urllib.parse import urlparse, parse_qs

# Value written to shifts.status when a manager approves an open shift.
# Check yours with:  SELECT DISTINCT status FROM shifts;
SHIFT_STATUS = "scheduled"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; frame-ancestors 'none'; base-uri 'none'")
SEC = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": CSP,
}

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Shift Exchange Portal</title>
<link rel="manifest" href="/manifest.json" crossorigin="use-credentials">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#0070f3">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Shifts">
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 14px 14px 90px; background: #f4f6f8; color: #222; max-width: 680px; margin: 0 auto; }
  h2 { margin: 6px 0 12px; } h3 { margin: 0 0 8px; }
  .card { background: #fff; padding: 14px; border-radius: 10px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,.06); }
  .row { border-bottom: 1px solid #eee; padding: 9px 0; } .row:last-child { border-bottom: none; }
  .btn { border: none; padding: 11px 14px; border-radius: 8px; font-weight: 600; font-size: 15px; background: #0070f3; color: #fff; margin: 6px 6px 0 0; }
  .btn.red { background: #d93025; } .btn.grey { background: #6b7280; } .btn:disabled { opacity: .5; }
  input, select { width: 100%; padding: 10px; font-size: 16px; margin: 4px 0 8px; border: 1px solid #ccc; border-radius: 8px; background: #fff; }
  .two { display: flex; gap: 8px; } .two > * { flex: 1; }
  .tag { font-size: 12px; background: #e8f0fe; color: #1a56c4; padding: 2px 8px; border-radius: 10px; }
  .tag.ok { background: #e6f4ea; color: #1e7e34; }
  .muted { color: #6b7280; font-size: 13px; }
  #err { color: #d93025; margin: 0 0 8px; min-height: 1em; font-weight: 600; }
  nav { position: fixed; bottom: 0; left: 0; right: 0; display: flex; background: #fff; border-top: 1px solid #ddd; padding-bottom: env(safe-area-inset-bottom); }
  nav button { flex: 1; padding: 14px 4px; border: none; background: none; font-size: 15px; color: #6b7280; font-weight: 600; }
  nav button.on { color: #0070f3; border-top: 3px solid #0070f3; padding-top: 11px; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; } td, th { padding: 6px 4px; border-bottom: 1px solid #eee; text-align: left; }
  .match { background: #fffbe6; border-radius: 8px; padding: 8px; margin: 6px 0; }
</style>
</head>
<body>
<h2>Shift Exchange</h2>
<div class="card" id="whoCard"><div id="who"></div><select id="userSel" style="display:none"></select></div>
<div id="err"></div>

<div class="tab" id="t_shifts">
  <div class="card" id="tradeCard" style="display:none"><h3>🔁 Trade offers for you</h3><div id="trades"></div></div>
  <div class="card" id="matchCard" style="display:none"><h3>⚡ Quick matches</h3><div id="matches"></div></div>
  <div class="card"><h3>My upcoming shifts</h3><div id="mine"></div></div>
  <div class="card">
    <h3>I can work extra</h3>
    <div class="muted">Post a day you are free. If someone needs that day off, you get matched.</div>
    <input type="date" id="offDate">
    <div class="two"><input type="time" id="offStart" value="00:00"><input type="time" id="offEnd" value="23:59"></div>
    <input type="text" id="offNote" placeholder="Note (optional)" maxlength="140">
    <button class="btn" onclick="postOffer()">Post availability</button>
    <div id="offers"></div>
  </div>
</div>

<div class="tab" id="t_board" style="display:none">
  <div class="card"><h3>Shifts people need covered</h3><div id="open"></div></div>
  <div class="card"><h3>Open shifts</h3><div id="openShifts"></div></div>
</div>

<div class="tab" id="t_mgr" style="display:none">
  <div class="card"><h3>Waiting for approval</h3><div id="pending"></div></div>
  <div class="card">
    <h3>Post an open shift</h3>
    <input type="date" id="osDate">
    <div class="two"><input type="time" id="osStart" value="09:00"><input type="time" id="osEnd" value="17:00"></div>
    <input type="text" id="osNote" placeholder="Note (optional)" maxlength="140">
    <button class="btn" onclick="postOpen()">Post open shift</button>
  </div>
  <div class="card">
    <h3>Report</h3>
    <div class="two"><input type="date" id="rFrom"><input type="date" id="rTo"></div>
    <button class="btn" onclick="runReport()">Run report</button>
    <button class="btn grey" onclick="csv()">Download CSV</button>
    <div id="report"></div>
  </div>
  <div class="card"><h3>Activity log</h3><div id="logs"></div></div>
</div>

<div class="tab" id="t_sched" style="display:none">
  <div class="card">
    <h3>Schedule</h3>
    <div class="two"><input type="date" id="sFrom"><input type="date" id="sTo"></div>
    <button class="btn" onclick="refresh()">Show</button>
    <div id="sched"></div>
  </div>
  <div class="card">
    <h3>Add a shift</h3>
    <select id="asUser"></select>
    <input type="date" id="asDate">
    <div class="two"><input type="time" id="asStart" value="09:00"><input type="time" id="asEnd" value="17:00"></div>
    <button class="btn" onclick="addShift()">Add shift</button>
  </div>
  <div class="card">
    <h3>People</h3>
    <div id="people"></div>
    <h3 style="margin-top:14px">Add a person</h3>
    <input type="text" id="auName" placeholder="Full name" maxlength="60">
    <input type="email" id="auEmail" placeholder="Their sign-in email" maxlength="120">
    <select id="auRole"><option value="employee">Employee</option><option value="manager">Manager</option></select>
    <button class="btn" onclick="addUser()">Add person</button>
  </div>
</div>

<nav>
  <button class="tabbtn" data-t="shifts">My shifts</button>
  <button class="tabbtn" data-t="board">Board</button>
  <button class="tabbtn" data-t="mgr" id="mgrBtn" style="display:none">Manager</button>
  <button class="tabbtn" data-t="sched" id="schedBtn" style="display:none">Schedule</button>
</nav>

<script>
let me = null, tab = 'shifts', demo = false, tradeables = [];
const $ = id => document.getElementById(id);
const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sh = r => '<b>' + esc(r.shift_date) + '</b> ' + esc(r.start_time) + '–' + esc(r.end_time);
const btn = (label, path, body, cls, ask) => '<button class="btn ' + (cls || '') + '" data-p="' + esc(path) + '" data-b="' + esc(JSON.stringify(body)) + '"' + (ask ? ' data-c="' + esc(ask) + '"' : '') + '>' + esc(label) + '</button>';
const none = t => '<p class="muted">' + t + '</p>';

async function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({'Content-Type': 'application/json'}, opts.headers || {});
  if (demo && me) opts.headers['X-User-Id'] = String(me.id);
  const res = await fetch(path, opts);
  const json = await res.json().catch(() => ({success: false, error: 'Server error'}));
  if (!json.success) { $('err').textContent = json.error || 'Error'; throw new Error(json.error); }
  $('err').textContent = '';
  return json.data;
}

document.addEventListener('click', async e => {
  const b = e.target.closest('button[data-p]');
  if (b) {
    if (b.dataset.c && !confirm(b.dataset.c)) return;
    b.disabled = true;
    try { await api(b.dataset.p, {method: 'POST', body: b.dataset.b || '{}'}); } catch (_) {}
    refresh();
  }
  const t = e.target.closest('.tabbtn');
  if (t) { tab = t.dataset.t; refresh(); }
});

async function init() {
  try {
    me = await api('/api/me');
  } catch (_) {
    // Not signed in: demo mode shows a picker
    try {
      demo = true;
      const users = await api('/api/users');
      const sel = $('userSel'); sel.style.display = '';
      sel.innerHTML = users.map(u => '<option value="' + u.id + '">' + esc(u.name) + ' (' + esc(u.role) + ')</option>').join('');
      const saved = localStorage.getItem('uid');
      if (saved && users.some(u => String(u.id) === saved)) sel.value = saved;
      const pick = () => { me = users.find(u => String(u.id) === sel.value); localStorage.setItem('uid', me.id); setMe(); refresh(); };
      sel.onchange = pick; pick(); return;
    } catch (_) { $('who').textContent = 'Not signed in.'; return; }
  }
  setMe(); refresh();
}
function setMe() {
  $('who').innerHTML = demo ? '<span class="muted">Test mode: sign in as</span>' : 'Signed in as <b>' + esc(me.name) + '</b> <span class="tag">' + esc(me.role) + '</span>';
  $('mgrBtn').style.display = me.role === 'manager' ? '' : 'none';
  $('schedBtn').style.display = me.role === 'manager' ? '' : 'none';
  if (me.role !== 'manager' && (tab === 'mgr' || tab === 'sched')) tab = 'shifts';
}

async function refresh() {
  if (!me) return;
  document.querySelectorAll('.tabbtn').forEach(b => b.classList.toggle('on', b.dataset.t === tab));
  document.querySelectorAll('.tab').forEach(s => s.style.display = s.id === 't_' + tab ? '' : 'none');
  try { await ({shifts: rShifts, board: rBoard, mgr: rMgr, sched: rSched})[tab](); } catch (_) {}
}

async function rShifts() {
  const [mine, matches, offers, trades, swappable] = await Promise.all([api('/api/my-shifts'), api('/api/matches'), api('/api/work-offers'), api('/api/trades'), api('/api/tradeable-shifts')]);
  tradeables = swappable;
  $('tradeCard').style.display = trades.length ? '' : 'none';
  $('trades').innerHTML = trades.map(t =>
    '<div class="match"><b>' + esc(t.requester_name) + '</b> offers <b>' + esc(t.give_date) + '</b> ' + esc(t.give_start) + '–' + esc(t.give_end) +
    '<br>for your <b>' + esc(t.get_date) + '</b> ' + esc(t.get_start) + '–' + esc(t.get_end) + '<br>' +
    btn('Accept', '/api/trade/accept', {requestId: t.id}) + btn('Decline', '/api/trade/decline', {requestId: t.id}, 'red') + '</div>').join('');
  $('matchCard').style.display = matches.length ? '' : 'none';
  $('matches').innerHTML = matches.map(m =>
    '<div class="match">' + sh(m) + '<div class="muted">' + esc(m.requester_name) + ' needs this off · ' + esc(m.worker_name) + ' can work it</div>' +
    btn('Connect & send to manager', '/api/match', {requestId: m.request_id, offerId: m.offer_id}) + '</div>').join('');
  $('mine').innerHTML = mine.length ? mine.map(s => {
    let act;
    if (s.req_status && s.req_by !== me.id) act = '<span class="tag">Part of a trade offer</span>';
    else if (s.req_status) act = '<span class="tag' + (s.req_status === 'claimed' ? ' ok' : '') + '">' +
      (s.req_status === 'claimed' ? 'Taken · waiting for manager' : (s.is_trade ? 'Trade offered · waiting for reply' : 'Waiting for someone to take it')) +
      '</span><br>' + btn('Cancel request', '/api/cancel-request', {requestId: s.req_id}, 'grey', 'Cancel this request?');
    else act = btn('I need this off', '/api/create-request', {shiftId: s.id}) +
      '<button class="btn grey" onclick="showTrade(' + s.id + ')">Trade…</button>' +
      '<div id="tr_' + s.id + '" style="display:none"><select id="trsel_' + s.id + '">' + tradeOptions() + '</select>' +
      '<button class="btn" onclick="sendTrade(' + s.id + ')">Send trade offer</button></div>';
    return '<div class="row">' + sh(s) + '<br>' + act + '</div>';
  }).join('') : none('No upcoming shifts.');
  $('offers').innerHTML = offers.map(o =>
    '<div class="row">' + sh(o) + ' <span class="tag">' + esc(o.status) + '</span>' +
    (o.status === 'open' ? '<br>' + btn('Cancel', '/api/work-offers/cancel', {id: o.id}, 'grey') : '') + '</div>').join('');
}

async function rBoard() {
  const [reqs, os] = await Promise.all([api('/api/requests'), api('/api/open-shifts')]);
  const open = reqs.filter(r => r.status === 'open');
  $('open').innerHTML = open.length ? open.map(r =>
    '<div class="row">' + sh(r) + '<div class="muted">From ' + esc(r.requester_name) + '</div>' +
    (r.requester_id !== me.id ? btn('Take this shift', '/api/claim', {requestId: r.id}) : '<span class="tag">Your request</span>') + '</div>').join('') : none('Nobody needs cover right now.');
  $('openShifts').innerHTML = os.length ? os.map(o =>
    '<div class="row">' + sh(o) + (o.note ? '<div class="muted">' + esc(o.note) + '</div>' : '') +
    (o.status === 'open' ? btn('Request this shift', '/api/open-shifts/take', {openShiftId: o.id}) :
     '<span class="tag">' + (o.claimed_by === me.id ? 'You requested it · waiting for manager' : 'Pending') + '</span>') + '</div>').join('') : none('No open shifts.');
}

async function rMgr() {
  const [p, logs] = await Promise.all([api('/api/pending'), api('/api/audit-logs')]);
  const a = p.swaps.map(r =>
    '<div class="row">' + sh(r) + '<div class="muted">' + (r.trade_date ? '🔁 ' + esc(r.requester_name) + ' gives this to ' + esc(r.claiming_name) + ' and gets ' + esc(r.trade_date) + ' ' + esc(r.trade_start) + '–' + esc(r.trade_end)
      : esc(r.requester_name) + ' → ' + esc(r.claiming_name)) + '</div>' +
    btn('Approve', '/api/approve', {requestId: r.id, decision: 'approve'}) + btn('Reject', '/api/approve', {requestId: r.id, decision: 'reject'}, 'red') + '</div>');
  const b = p.openShifts.map(o =>
    '<div class="row">' + sh(o) + '<div class="muted">Open shift → ' + esc(o.claimed_name) + '</div>' +
    btn('Approve', '/api/open-shifts/decide', {openShiftId: o.id, decision: 'approve'}) + btn('Reject', '/api/open-shifts/decide', {openShiftId: o.id, decision: 'reject'}, 'red') + '</div>');
  $('pending').innerHTML = a.concat(b).join('') || none('Nothing waiting.');
  $('logs').innerHTML = logs.map(l => '<div class="row muted">' + esc(l.kind) + ' #' + esc(l.ref) + ' · <b>' + esc(l.action_taken) + '</b> by ' + esc(l.actor_name) +
    '<br>' + esc(l.log_notes) + ' · ' + esc(l.timestamp) + '</div>').join('') || none('No activity yet.');
  if (!$('rFrom').value) {
    const d = new Date(), y = d.getFullYear(), m = d.getMonth(), pad = n => String(n).padStart(2, '0');
    $('rFrom').value = y + '-' + pad(m + 1) + '-01';
    $('rTo').value = y + '-' + pad(m + 1) + '-' + pad(new Date(y, m + 1, 0).getDate());
  }
}

function postOffer() {
  api('/api/work-offers', {method: 'POST', body: JSON.stringify({date: $('offDate').value, start: $('offStart').value, end: $('offEnd').value, note: $('offNote').value})})
    .then(() => { $('offNote').value = ''; refresh(); }).catch(() => {});
}
function postOpen() {
  api('/api/open-shifts', {method: 'POST', body: JSON.stringify({date: $('osDate').value, start: $('osStart').value, end: $('osEnd').value, note: $('osNote').value})})
    .then(() => { $('osNote').value = ''; refresh(); }).catch(() => {});
}
async function runReport() {
  const r = await api('/api/report?from=' + $('rFrom').value + '&to=' + $('rTo').value);
  const s = r.summary;
  $('report').innerHTML =
    '<p><b>' + s.approved + '</b> swaps approved · <b>' + s.rejected + '</b> rejected · <b>' + s.withdrawn + '</b> withdrawn · <b>' + s.pending + '</b> pending · <b>' + s.open_filled + '</b> open shifts filled</p>' +
    '<table><tr><th>Employee</th><th>Gave away</th><th>Took over</th><th>Open</th></tr>' +
    r.employees.map(e => '<tr><td>' + esc(e.name) + '</td><td>' + e.gave_away + '</td><td>' + e.took_over + '</td><td>' + e.picked_open + '</td></tr>').join('') + '</table>' +
    '<h3 style="margin-top:12px">Completed changes</h3>' +
    (r.rows.map(x => '<div class="row">' + sh(x) + '<div class="muted">' + (x.kind === 'trade' ? esc(x.gave) + ' ⇄ ' + esc(x.took) + ' (also ' + esc(x.other_date) + ')' : esc(x.gave) + ' → ' + esc(x.took)) + ' · approved by ' + esc(x.approved_by) + '</div></div>').join('') || none('None in this range.'));
}
async function csv() {
  const res = await fetch('/api/report.csv?from=' + $('rFrom').value + '&to=' + $('rTo').value, {headers: demo ? {'X-User-Id': String(me.id)} : {}});
  if (!res.ok) { $('err').textContent = 'Could not export'; return; }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a'); a.href = url; a.download = 'shift-report.csv'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function tradeOptions() {
  return tradeables.length ? tradeables.map(t => '<option value="' + t.id + '">' + esc(t.owner_name) + ' · ' + esc(t.shift_date) + ' ' + esc(t.start_time) + '–' + esc(t.end_time) + '</option>').join('')
    : '<option value="">No shifts available to trade for</option>';
}
function showTrade(id) { const d = $('tr_' + id); d.style.display = d.style.display === 'none' ? '' : 'none'; }
function sendTrade(id) {
  const target = Number($('trsel_' + id).value);
  if (!target) { $('err').textContent = 'Pick a shift to trade for'; return; }
  api('/api/create-trade', {method: 'POST', body: JSON.stringify({shiftId: id, targetShiftId: target})}).then(refresh).catch(() => {});
}

// ----- Manager: schedule + people -----
const ymd = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
async function rSched() {
  if (!$('sFrom').value) { const d = new Date(); $('sFrom').value = ymd(d); d.setDate(d.getDate() + 13); $('sTo').value = ymd(d); }
  const [users, shifts] = await Promise.all([api('/api/admin/users'), api('/api/admin/shifts?from=' + $('sFrom').value + '&to=' + $('sTo').value)]);
  const active = users.filter(u => u.active);
  const opts = id => active.map(u => '<option value="' + u.id + '"' + (u.id === id ? ' selected' : '') + '>' + esc(u.name) + '</option>').join('');
  $('sched').innerHTML = shifts.length ? shifts.map(s =>
    '<div class="row">' + sh(s) + ' · <b>' + esc(s.user_name) + '</b>' +
    (s.locked ? ' <span class="tag">open request</span>' :
      '<div class="two"><select id="re_' + s.id + '">' + opts(s.user_id) + '</select>' +
      '<button class="btn grey" onclick="reassign(' + s.id + ')">Reassign</button></div>' +
      btn('Delete shift', '/api/admin/shifts/delete', {id: s.id}, 'red', 'Delete this shift?')) + '</div>').join('') : none('No shifts in this range.');
  const keep = $('asUser').value;
  $('asUser').innerHTML = opts(0);
  if (keep) $('asUser').value = keep;
  $('people').innerHTML = users.map(u =>
    '<div class="row"><b>' + esc(u.name) + '</b> <span class="tag">' + esc(u.role) + '</span>' + (u.active ? '' : ' <span class="tag">inactive</span>') +
    '<div class="muted">' + esc(u.email) + ' · ' + u.upcoming + ' upcoming shifts</div>' +
    (u.id === me.id ? '' :
      (u.active ? btn('Deactivate', '/api/admin/users/update', {id: u.id, active: 0}, 'grey', 'Deactivate ' + u.name + '? They will no longer be able to sign in.')
                : btn('Reactivate', '/api/admin/users/update', {id: u.id, active: 1})) +
      btn(u.role === 'manager' ? 'Make employee' : 'Make manager', '/api/admin/users/update', {id: u.id, role: u.role === 'manager' ? 'employee' : 'manager'}, 'grey')) + '</div>').join('');
}
function reassign(id) {
  api('/api/admin/shifts/update', {method: 'POST', body: JSON.stringify({id: id, userId: Number($('re_' + id).value)})}).then(refresh).catch(() => {});
}
function addShift() {
  api('/api/admin/shifts', {method: 'POST', body: JSON.stringify({userId: Number($('asUser').value), date: $('asDate').value, start: $('asStart').value, end: $('asEnd').value})}).then(refresh).catch(() => {});
}
function addUser() {
  api('/api/admin/users', {method: 'POST', body: JSON.stringify({name: $('auName').value, email: $('auEmail').value, role: $('auRole').value})})
    .then(() => { $('auName').value = ''; $('auEmail').value = ''; refresh(); }).catch(() => {});
}

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
init();
</script>
</body>
</html>
"""


def jres(payload, status=200):
    headers = dict(SEC)
    headers["Content-Type"] = "application/json"
    headers["Cache-Control"] = "no-store"
    return Response(json.dumps(payload), status=status, headers=headers)


def ok(data=None):
    return jres({"success": True, "data": data})


def fail(msg, status=400):
    return jres({"success": False, "error": msg}, status)


def to_rows(result):
    r = result.results
    return r.to_py() if hasattr(r, "to_py") else list(r)


def changes(result):
    try:
        return int(result.meta.changes)
    except Exception:
        return 0


def csv_cell(v):
    s = "" if v is None else str(v)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):  # block spreadsheet formula injection
        s = "'" + s
    return '"' + s.replace('"', '""') + '"'


def valid_range(start, end):
    return bool(TIME_RE.match(start or "")) and bool(TIME_RE.match(end or "")) and start < end


class Default(WorkerEntrypoint):
    # ---------- helpers ----------
    async def q(self, sql, *params):
        res = await self.env.DB.prepare(sql).bind(*params).all()
        return to_rows(res)

    def st(self, sql, *params):
        return self.env.DB.prepare(sql).bind(*params)

    def log_swap(self, req_id, uid, action, notes):
        return self.st(
            "INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) VALUES (?, ?, ?, ?)",
            req_id, uid, action, notes)

    def log_act(self, kind, ref_id, uid, action, notes):
        return self.st(
            "INSERT INTO activity_log (ref_type, ref_id, action_by, action_taken, log_notes) VALUES (?, ?, ?, ?, ?)",
            kind, ref_id, uid, action, notes)

    async def has_conflict(self, uid, date, start, end, exclude=0):
        """True if uid already works an overlapping shift (ignoring shift id `exclude`)."""
        rows = await self.q(
            "SELECT 1 AS x FROM shifts WHERE user_id = ? AND shift_date = ? AND start_time < ? AND end_time > ? "
            "AND id != ? LIMIT 1",
            uid, date, end, start, exclude or 0)
        return bool(rows)

    async def active_request(self, shift_id):
        """True if the shift is part of an open/claimed swap or trade."""
        rows = await self.q(
            "SELECT id FROM shift_requests WHERE (original_shift_id = ? OR trade_shift_id = ?) "
            "AND status IN ('open', 'claimed') LIMIT 1", shift_id, shift_id)
        return bool(rows)

    def demo_mode(self):
        try:
            return str(self.env.DEMO_MODE).lower() == "true"
        except Exception:
            return False

    async def current_user(self, request, demo):
        """Cloudflare Access email header is the secure identity.
        X-User-Id is accepted ONLY while DEMO_MODE = "true" (anyone can fake it)."""
        email = request.headers.get("Cf-Access-Authenticated-User-Email")
        if email:
            rows = await self.q("SELECT id, name, email, role FROM users WHERE lower(email) = lower(?) AND active = 1", email)
            return rows[0] if rows else None
        if demo:
            try:
                uid = int(request.headers.get("X-User-Id") or 0)
            except ValueError:
                uid = 0
            if uid:
                rows = await self.q("SELECT id, name, email, role FROM users WHERE id = ? AND active = 1", uid)
                return rows[0] if rows else None
        return None

    # ---------- reporting ----------
    async def build_report(self, frm, to):
        sw = await self.q("""
            SELECT CASE WHEN sr.closed_reason IS NOT NULL THEN 'withdrawn' ELSE sr.status END AS status,
                   COUNT(*) AS c FROM shift_requests sr
            JOIN shifts s ON s.id = sr.original_shift_id
            WHERE s.shift_date BETWEEN ? AND ? GROUP BY 1""", frm, to)
        counts = {r["status"]: r["c"] for r in sw}
        filled = await self.q(
            "SELECT COUNT(*) AS c FROM open_shifts WHERE status = 'filled' AND shift_date BETWEEN ? AND ?", frm, to)
        summary = {
            "approved": counts.get("approved", 0),
            "rejected": counts.get("rejected", 0),
            "withdrawn": counts.get("withdrawn", 0),
            "pending": counts.get("open", 0) + counts.get("claimed", 0),
            "open_filled": filled[0]["c"] if filled else 0,
        }
        employees = await self.q("""
            SELECT u.id, u.name,
              (SELECT COUNT(*) FROM shift_requests sr JOIN shifts s ON s.id = sr.original_shift_id
                 WHERE sr.requester_id = u.id AND sr.status = 'approved' AND s.shift_date BETWEEN ? AND ?) AS gave_away,
              (SELECT COUNT(*) FROM shift_requests sr JOIN shifts s ON s.id = sr.original_shift_id
                 WHERE sr.claiming_user_id = u.id AND sr.status = 'approved' AND s.shift_date BETWEEN ? AND ?) AS took_over,
              (SELECT COUNT(*) FROM open_shifts o
                 WHERE o.claimed_by = u.id AND o.status = 'filled' AND o.shift_date BETWEEN ? AND ?) AS picked_open
            FROM users u WHERE u.role = 'employee' ORDER BY u.name""", frm, to, frm, to, frm, to)
        rows = await self.q("""
            SELECT * FROM (
              SELECT CASE WHEN sr.trade_shift_id IS NULL THEN 'swap' ELSE 'trade' END AS kind,
                     sr.id AS ref, s.shift_date, s.start_time, s.end_time,
                     u1.name AS gave, u2.name AS took, m.name AS approved_by,
                     (SELECT MAX(l.timestamp) FROM shift_audit_logs l
                        WHERE l.request_id = sr.id AND l.action_taken = 'APPROVED') AS approved_at,
                     t.shift_date AS other_date, t.start_time AS other_start, t.end_time AS other_end
              FROM shift_requests sr
              JOIN shifts s ON s.id = sr.original_shift_id
              LEFT JOIN shifts t ON t.id = sr.trade_shift_id
              JOIN users u1 ON u1.id = sr.requester_id
              LEFT JOIN users u2 ON u2.id = sr.claiming_user_id
              LEFT JOIN users m ON m.id = sr.manager_id
              WHERE sr.status = 'approved' AND s.shift_date BETWEEN ? AND ?
              UNION ALL
              SELECT 'open_shift', o.id, o.shift_date, o.start_time, o.end_time,
                     'Open shift', u.name, m.name,
                     (SELECT MAX(a.timestamp) FROM activity_log a
                        WHERE a.ref_type = 'open_shift' AND a.ref_id = o.id AND a.action_taken = 'APPROVED'),
                     NULL, NULL, NULL
              FROM open_shifts o
              JOIN users u ON u.id = o.claimed_by
              LEFT JOIN users m ON m.id = o.manager_id
              WHERE o.status = 'filled' AND o.shift_date BETWEEN ? AND ?
            ) ORDER BY shift_date DESC""", frm, to, frm, to)
        return {"summary": summary, "employees": employees, "rows": rows}

    # ---------- main entry ----------
    async def fetch(self, request):
        parsed = urlparse(request.url)
        path = parsed.path
        qs = parse_qs(parsed.query)
        method = request.method
        db = self.env.DB

        if path == "/" and method == "GET":
            headers = dict(SEC)
            headers["Content-Type"] = "text/html;charset=UTF-8"
            return Response(HTML, headers=headers)

        if not path.startswith("/api/"):
            return Response("Not Found", status=404)

        demo = self.demo_mode()
        if demo and path == "/api/users" and method == "GET":
            return ok(await self.q("SELECT id, name, role FROM users ORDER BY name"))

        user = await self.current_user(request, demo)
        if not user:
            return fail("Not signed in", 401)
        is_mgr = user["role"] == "manager"
        uid = user["id"]

        body = {}
        if method == "POST":
            if "application/json" not in (request.headers.get("Content-Type") or ""):
                return fail("JSON required", 415)  # also blocks cross-site form posts
            try:
                body = await request.json()
                if hasattr(body, "to_py"):
                    body = body.to_py()
                if not isinstance(body, dict):
                    return fail("Invalid JSON")
            except Exception:
                return fail("Invalid JSON")

        if path == "/api/me" and method == "GET":
            return ok({"id": uid, "name": user["name"], "role": user["role"]})

        # ===== Swap requests =====
        if path == "/api/requests" and method == "GET":
            return ok(await self.q("""
                SELECT sr.id, sr.status, sr.requester_id, sr.claiming_user_id,
                       s.shift_date, s.start_time, s.end_time,
                       u1.name AS requester_name, u2.name AS claiming_name
                FROM shift_requests sr
                JOIN shifts s ON sr.original_shift_id = s.id
                JOIN users u1 ON sr.requester_id = u1.id
                LEFT JOIN users u2 ON sr.claiming_user_id = u2.id
                WHERE sr.status = 'open' AND sr.trade_shift_id IS NULL AND s.shift_date >= date('now')
                ORDER BY s.shift_date, sr.id DESC LIMIT 200"""))

        if path == "/api/my-shifts" and method == "GET":
            return ok(await self.q("""
                SELECT s.id, s.shift_date, s.start_time, s.end_time,
                       sr.id AS req_id, sr.status AS req_status, sr.requester_id AS req_by,
                       (sr.trade_shift_id IS NOT NULL) AS is_trade
                FROM shifts s
                LEFT JOIN shift_requests sr
                  ON (sr.original_shift_id = s.id OR sr.trade_shift_id = s.id) AND sr.status IN ('open', 'claimed')
                WHERE s.user_id = ? AND s.shift_date >= date('now')
                ORDER BY s.shift_date, s.start_time""", uid))

        if path == "/api/create-request" and method == "POST":
            shift_id = body.get("shiftId")
            if not await self.q("SELECT id FROM shifts WHERE id = ? AND user_id = ?", shift_id, uid):
                return fail("You can only offer your own shifts", 403)
            if await self.active_request(shift_id):
                return fail("This shift already has an active request", 409)
            res = await self.st(
                "INSERT INTO shift_requests (request_type, original_shift_id, requester_id, status) "
                "VALUES ('giveaway', ?, ?, 'open')", shift_id, uid).run()
            new_id = res.meta.last_row_id
            await self.log_swap(new_id, uid, "CREATED", "Employee needs this shift off").run()
            return ok({"id": new_id})

        if path == "/api/claim" and method == "POST":
            req_id = body.get("requestId")
            rows = await self.q("""
                SELECT sr.requester_id, s.shift_date, s.start_time, s.end_time
                FROM shift_requests sr JOIN shifts s ON s.id = sr.original_shift_id
                WHERE sr.id = ? AND sr.status = 'open' AND sr.trade_shift_id IS NULL""", req_id)
            if not rows:
                return fail("Request is no longer open", 409)
            r = rows[0]
            if r["requester_id"] == uid:
                return fail("You cannot take your own shift", 400)
            if await self.has_conflict(uid, r["shift_date"], r["start_time"], r["end_time"]):
                return fail("You already work during that time", 409)
            res = await self.st(
                "UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed' "
                "WHERE id = ? AND status = 'open' AND requester_id != ? AND trade_shift_id IS NULL",
                uid, req_id, uid).run()
            if changes(res) == 0:
                return fail("Someone else just took it", 409)
            await self.log_swap(req_id, uid, "CLAIMED", "Employee offered to take the shift").run()
            return ok()

        # ===== Work offers ("I can work") + quick matching =====
        if path == "/api/work-offers" and method == "GET":
            return ok(await self.q(
                "SELECT id, shift_date, start_time, end_time, note, status FROM work_offers "
                "WHERE user_id = ? AND status != 'cancelled' AND shift_date >= date('now') "
                "ORDER BY shift_date", uid))

        if path == "/api/work-offers" and method == "POST":
            date = body.get("date") or ""
            start = body.get("start") or "00:00"
            end = body.get("end") or "23:59"
            note = str(body.get("note") or "")[:140]
            if not DATE_RE.match(date):
                return fail("Pick a date")
            if not valid_range(start, end):
                return fail("End time must be after start time")
            res = await self.st(
                "INSERT INTO work_offers (user_id, shift_date, start_time, end_time, note) VALUES (?, ?, ?, ?, ?)",
                uid, date, start, end, note).run()
            await self.log_act("work_offer", res.meta.last_row_id, uid, "POSTED",
                               "Available " + date + " " + start + "-" + end).run()
            return ok({"id": res.meta.last_row_id})

        if path == "/api/work-offers/cancel" and method == "POST":
            oid = body.get("id")
            res = await self.st(
                "UPDATE work_offers SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status = 'open'",
                oid, uid).run()
            if changes(res) == 0:
                return fail("Cannot cancel this", 409)
            await self.log_act("work_offer", oid, uid, "CANCELLED", "Availability withdrawn").run()
            return ok()

        if path == "/api/matches" and method == "GET":
            return ok(await self.q("""
                SELECT sr.id AS request_id, wo.id AS offer_id,
                       s.shift_date, s.start_time, s.end_time,
                       u1.name AS requester_name, u2.name AS worker_name
                FROM shift_requests sr
                JOIN shifts s ON s.id = sr.original_shift_id
                JOIN users u1 ON u1.id = sr.requester_id
                JOIN work_offers wo ON wo.shift_date = s.shift_date AND wo.status = 'open'
                     AND wo.user_id != sr.requester_id
                     AND wo.start_time <= s.start_time AND wo.end_time >= s.end_time
                JOIN users u2 ON u2.id = wo.user_id
                WHERE sr.status = 'open' AND sr.trade_shift_id IS NULL
                  AND (sr.requester_id = ? OR wo.user_id = ? OR ? = 'manager')
                ORDER BY s.shift_date LIMIT 50""", uid, uid, user["role"]))

        if path == "/api/match" and method == "POST":
            rid, oid = body.get("requestId"), body.get("offerId")
            reqs = await self.q("""
                SELECT sr.requester_id, sr.status, sr.trade_shift_id, s.shift_date, s.start_time, s.end_time
                FROM shift_requests sr JOIN shifts s ON s.id = sr.original_shift_id WHERE sr.id = ?""", rid)
            offs = await self.q("SELECT user_id, status, shift_date, start_time, end_time "
                                "FROM work_offers WHERE id = ?", oid)
            if not reqs or not offs:
                return fail("Not found", 404)
            r, o = reqs[0], offs[0]
            if r["trade_shift_id"]:
                return fail("Trade offers can't be matched this way", 400)
            if r["status"] != "open" or o["status"] != "open":
                return fail("One of these is no longer available", 409)
            if uid not in (r["requester_id"], o["user_id"]) and not is_mgr:
                return fail("Not allowed", 403)
            if (o["user_id"] == r["requester_id"] or o["shift_date"] != r["shift_date"]
                    or o["start_time"] > r["start_time"] or o["end_time"] < r["end_time"]):
                return fail("These do not match", 400)
            if await self.has_conflict(o["user_id"], r["shift_date"], r["start_time"], r["end_time"]):
                return fail("That employee already works during that time", 409)
            res = await self.st(
                "UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed' WHERE id = ? AND status = 'open'",
                o["user_id"], rid).run()
            if changes(res) == 0:
                return fail("Someone else just took it", 409)
            await db.batch(to_js([
                self.st("UPDATE work_offers SET status = 'matched', matched_request_id = ? "
                        "WHERE id = ? AND status = 'open'", rid, oid),
                self.log_swap(rid, uid, "MATCHED", "Linked to availability post #" + str(oid)),
                self.log_act("work_offer", oid, uid, "MATCHED", "Matched to swap request #" + str(rid)),
            ]))
            return ok()

        # ===== Open shifts =====
        if path == "/api/open-shifts" and method == "GET":
            return ok(await self.q("""
                SELECT id, shift_date, start_time, end_time, note, status, claimed_by
                FROM open_shifts
                WHERE status IN ('open', 'pending') AND shift_date >= date('now')
                ORDER BY shift_date, start_time"""))

        if path == "/api/open-shifts" and method == "POST":
            if not is_mgr:
                return fail("Managers only", 403)
            date, start, end = body.get("date") or "", body.get("start") or "", body.get("end") or ""
            note = str(body.get("note") or "")[:140]
            if not DATE_RE.match(date) or not valid_range(start, end):
                return fail("Check the date and times")
            res = await self.st(
                "INSERT INTO open_shifts (shift_date, start_time, end_time, note, posted_by) VALUES (?, ?, ?, ?, ?)",
                date, start, end, note, uid).run()
            await self.log_act("open_shift", res.meta.last_row_id, uid, "POSTED",
                               "Open shift " + date + " " + start + "-" + end).run()
            return ok({"id": res.meta.last_row_id})

        if path == "/api/open-shifts/take" and method == "POST":
            osid = body.get("openShiftId")
            rows = await self.q("SELECT shift_date, start_time, end_time FROM open_shifts "
                                "WHERE id = ? AND status = 'open'", osid)
            if not rows:
                return fail("That shift is no longer open", 409)
            o = rows[0]
            if await self.has_conflict(uid, o["shift_date"], o["start_time"], o["end_time"]):
                return fail("You already work during that time", 409)
            res = await self.st(
                "UPDATE open_shifts SET status = 'pending', claimed_by = ? WHERE id = ? AND status = 'open'",
                uid, osid).run()
            if changes(res) == 0:
                return fail("Someone else just requested it", 409)
            await self.log_act("open_shift", osid, uid, "REQUESTED", "Employee requested this open shift").run()
            return ok()

        # ===== Manager approvals =====
        if path == "/api/pending" and method == "GET":
            if not is_mgr:
                return fail("Managers only", 403)
            swaps = await self.q("""
                SELECT sr.id, s.shift_date, s.start_time, s.end_time,
                       u1.name AS requester_name, u2.name AS claiming_name,
                       t.shift_date AS trade_date, t.start_time AS trade_start, t.end_time AS trade_end
                FROM shift_requests sr
                JOIN shifts s ON s.id = sr.original_shift_id
                JOIN users u1 ON u1.id = sr.requester_id
                JOIN users u2 ON u2.id = sr.claiming_user_id
                LEFT JOIN shifts t ON t.id = sr.trade_shift_id
                WHERE sr.status = 'claimed' ORDER BY s.shift_date""")
            opens = await self.q("""
                SELECT o.id, o.shift_date, o.start_time, o.end_time, u.name AS claimed_name
                FROM open_shifts o JOIN users u ON u.id = o.claimed_by
                WHERE o.status = 'pending' ORDER BY o.shift_date""")
            return ok({"swaps": swaps, "openShifts": opens})

        if path == "/api/approve" and method == "POST":
            if not is_mgr:
                return fail("Managers only", 403)
            rid, decision = body.get("requestId"), body.get("decision")
            if decision not in ("approve", "reject"):
                return fail("decision must be 'approve' or 'reject'")
            rows = await self.q("""
                SELECT sr.requester_id, sr.original_shift_id, sr.claiming_user_id, sr.trade_shift_id,
                       s.shift_date, s.start_time, s.end_time, s.user_id AS s_owner,
                       t.shift_date AS t_date, t.start_time AS t_start, t.end_time AS t_end, t.user_id AS t_owner
                FROM shift_requests sr
                JOIN shifts s ON s.id = sr.original_shift_id
                LEFT JOIN shifts t ON t.id = sr.trade_shift_id
                WHERE sr.id = ? AND sr.status = 'claimed'""", rid)
            if not rows:
                return fail("Request is not awaiting approval", 409)
            r = rows[0]
            if decision == "approve":
                if r["s_owner"] != r["requester_id"]:
                    return fail("That shift changed hands; cancel this request", 409)
                if r["trade_shift_id"]:
                    if r["t_owner"] != r["claiming_user_id"]:
                        return fail("The other shift changed hands; cancel this request", 409)
                    if (await self.has_conflict(r["claiming_user_id"], r["shift_date"], r["start_time"],
                                                r["end_time"], r["trade_shift_id"])
                            or await self.has_conflict(r["requester_id"], r["t_date"], r["t_start"],
                                                       r["t_end"], r["original_shift_id"])):
                        return fail("One of them now has a conflicting shift", 409)
                    stmts = [
                        self.st("UPDATE shifts SET user_id = ? WHERE id = ? AND user_id = ?",
                                r["claiming_user_id"], r["original_shift_id"], r["requester_id"]),
                        self.st("UPDATE shifts SET user_id = ? WHERE id = ? AND user_id = ?",
                                r["requester_id"], r["trade_shift_id"], r["claiming_user_id"]),
                        self.st("UPDATE shift_requests SET status = 'approved', manager_id = ? "
                                "WHERE id = ? AND status = 'claimed'", uid, rid),
                        self.log_swap(rid, uid, "APPROVED", "Manager approved the trade"),
                    ]
                else:
                    if await self.has_conflict(r["claiming_user_id"], r["shift_date"], r["start_time"], r["end_time"]):
                        return fail("The new employee now has a conflicting shift", 409)
                    stmts = [
                        self.st("UPDATE shifts SET user_id = ? WHERE id = ? AND user_id = ?",
                                r["claiming_user_id"], r["original_shift_id"], r["requester_id"]),
                        self.st("UPDATE shift_requests SET status = 'approved', manager_id = ? "
                                "WHERE id = ? AND status = 'claimed'", uid, rid),
                        self.log_swap(rid, uid, "APPROVED", "Manager approved the swap"),
                    ]
            else:
                stmts = [
                    self.st("UPDATE shift_requests SET status = 'rejected', manager_id = ? "
                            "WHERE id = ? AND status = 'claimed'", uid, rid),
                    self.st("UPDATE work_offers SET status = 'open', matched_request_id = NULL "
                            "WHERE matched_request_id = ? AND status = 'matched'", rid),
                    self.log_swap(rid, uid, "REJECTED", "Manager rejected the request"),
                ]
            await db.batch(to_js(stmts))  # all-or-nothing
            return ok()

        if path == "/api/open-shifts/decide" and method == "POST":
            if not is_mgr:
                return fail("Managers only", 403)
            osid, decision = body.get("openShiftId"), body.get("decision")
            if decision not in ("approve", "reject"):
                return fail("decision must be 'approve' or 'reject'")
            rows = await self.q("SELECT shift_date, start_time, end_time, claimed_by FROM open_shifts "
                                "WHERE id = ? AND status = 'pending'", osid)
            if not rows:
                return fail("Not awaiting approval", 409)
            o = rows[0]
            if decision == "approve":
                if await self.has_conflict(o["claimed_by"], o["shift_date"], o["start_time"], o["end_time"]):
                    return fail("That employee now has a conflicting shift", 409)
                stmts = [
                    self.st("UPDATE open_shifts SET status = 'filled', manager_id = ? "
                            "WHERE id = ? AND status = 'pending'", uid, osid),
                    self.st("INSERT INTO shifts (user_id, shift_date, start_time, end_time, status) "
                            "VALUES (?, ?, ?, ?, ?)", o["claimed_by"], o["shift_date"], o["start_time"],
                            o["end_time"], SHIFT_STATUS),
                    self.log_act("open_shift", osid, uid, "APPROVED", "Manager approved the open shift"),
                ]
            else:
                stmts = [
                    self.st("UPDATE open_shifts SET status = 'open', claimed_by = NULL "
                            "WHERE id = ? AND status = 'pending'", osid),
                    self.log_act("open_shift", osid, uid, "REJECTED", "Manager rejected; shift is open again"),
                ]
            await db.batch(to_js(stmts))
            return ok()

        # ===== Cancel + swap-for-swap trades =====
        if path == "/api/cancel-request" and method == "POST":
            rid = body.get("requestId")
            rows = await self.q("SELECT requester_id, status FROM shift_requests WHERE id = ?", rid)
            if not rows:
                return fail("Not found", 404)
            if rows[0]["requester_id"] != uid and not is_mgr:
                return fail("Not allowed", 403)
            res = await self.st(
                "UPDATE shift_requests SET status = 'rejected', closed_reason = 'cancelled' "
                "WHERE id = ? AND status IN ('open', 'claimed')", rid).run()
            if changes(res) == 0:
                return fail("This request is already closed", 409)
            await db.batch(to_js([
                self.st("UPDATE work_offers SET status = 'open', matched_request_id = NULL "
                        "WHERE matched_request_id = ? AND status = 'matched'", rid),
                self.log_swap(rid, uid, "CANCELLED", "Request cancelled"),
            ]))
            return ok()

        if path == "/api/tradeable-shifts" and method == "GET":
            return ok(await self.q("""
                SELECT s.id, s.shift_date, s.start_time, s.end_time, u.name AS owner_name
                FROM shifts s JOIN users u ON u.id = s.user_id
                WHERE s.user_id != ? AND u.active = 1 AND s.shift_date >= date('now')
                  AND NOT EXISTS (SELECT 1 FROM shift_requests sr
                                  WHERE (sr.original_shift_id = s.id OR sr.trade_shift_id = s.id)
                                    AND sr.status IN ('open', 'claimed'))
                ORDER BY s.shift_date, s.start_time LIMIT 150""", uid))

        if path == "/api/trades" and method == "GET":
            return ok(await self.q("""
                SELECT sr.id, u1.name AS requester_name,
                       s.shift_date AS give_date, s.start_time AS give_start, s.end_time AS give_end,
                       t.shift_date AS get_date, t.start_time AS get_start, t.end_time AS get_end
                FROM shift_requests sr
                JOIN users u1 ON u1.id = sr.requester_id
                JOIN shifts s ON s.id = sr.original_shift_id
                JOIN shifts t ON t.id = sr.trade_shift_id
                WHERE sr.status = 'open' AND sr.target_user_id = ?
                ORDER BY s.shift_date""", uid))

        if path == "/api/create-trade" and method == "POST":
            mine_id, theirs_id = body.get("shiftId"), body.get("targetShiftId")
            mine = await self.q("SELECT id, shift_date, start_time, end_time FROM shifts "
                                "WHERE id = ? AND user_id = ?", mine_id, uid)
            theirs = await self.q("""
                SELECT s.id, s.user_id, s.shift_date, s.start_time, s.end_time
                FROM shifts s JOIN users u ON u.id = s.user_id
                WHERE s.id = ? AND s.user_id != ? AND u.active = 1""", theirs_id, uid)
            if not mine or not theirs:
                return fail("Pick one of your shifts and one of theirs")
            m, t = mine[0], theirs[0]
            if await self.active_request(mine_id) or await self.active_request(theirs_id):
                return fail("One of those shifts already has an active request", 409)
            if await self.has_conflict(uid, t["shift_date"], t["start_time"], t["end_time"], m["id"]):
                return fail("You already work during that shift's time", 409)
            if await self.has_conflict(t["user_id"], m["shift_date"], m["start_time"], m["end_time"], t["id"]):
                return fail("They already work during your shift's time", 409)
            res = await self.st(
                "INSERT INTO shift_requests (request_type, original_shift_id, requester_id, status, "
                "trade_shift_id, target_user_id) VALUES ('giveaway', ?, ?, 'open', ?, ?)",
                mine_id, uid, theirs_id, t["user_id"]).run()
            await self.log_swap(res.meta.last_row_id, uid, "TRADE_OFFERED",
                                "Offered a trade for shift #" + str(theirs_id)).run()
            return ok({"id": res.meta.last_row_id})

        if path == "/api/trade/accept" and method == "POST":
            rid = body.get("requestId")
            rows = await self.q("""
                SELECT sr.trade_shift_id, s.shift_date, s.start_time, s.end_time
                FROM shift_requests sr JOIN shifts s ON s.id = sr.original_shift_id
                WHERE sr.id = ? AND sr.status = 'open' AND sr.target_user_id = ?""", rid, uid)
            if not rows:
                return fail("This offer is no longer available", 409)
            r = rows[0]
            if await self.has_conflict(uid, r["shift_date"], r["start_time"], r["end_time"], r["trade_shift_id"]):
                return fail("You already work during that time", 409)
            res = await self.st(
                "UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed' "
                "WHERE id = ? AND status = 'open' AND target_user_id = ?", uid, rid, uid).run()
            if changes(res) == 0:
                return fail("This offer is no longer available", 409)
            await self.log_swap(rid, uid, "TRADE_ACCEPTED", "Coworker accepted the trade").run()
            return ok()

        if path == "/api/trade/decline" and method == "POST":
            rid = body.get("requestId")
            res = await self.st(
                "UPDATE shift_requests SET status = 'rejected', closed_reason = 'declined' "
                "WHERE id = ? AND status = 'open' AND target_user_id = ?", rid, uid).run()
            if changes(res) == 0:
                return fail("This offer is no longer available", 409)
            await self.log_swap(rid, uid, "TRADE_DECLINED", "Coworker declined the trade").run()
            return ok()

        # ===== Manager admin: people + schedule =====
        if path.startswith("/api/admin/"):
            if not is_mgr:
                return fail("Managers only", 403)

            if path == "/api/admin/users" and method == "GET":
                return ok(await self.q("""
                    SELECT u.id, u.name, u.email, u.role, u.active,
                           (SELECT COUNT(*) FROM shifts s WHERE s.user_id = u.id AND s.shift_date >= date('now')) AS upcoming
                    FROM users u ORDER BY u.active DESC, u.name"""))

            if path == "/api/admin/users" and method == "POST":
                name = str(body.get("name") or "").strip()
                email = str(body.get("email") or "").strip()
                role = body.get("role")
                if not (1 <= len(name) <= 60) or not EMAIL_RE.match(email) or role not in ("employee", "manager"):
                    return fail("Enter a name, a valid email, and a role")
                if await self.q("SELECT id FROM users WHERE lower(email) = lower(?)", email):
                    return fail("That email is already in use", 409)
                res = await self.st("INSERT INTO users (name, email, role) VALUES (?, ?, ?)", name, email, role).run()
                await self.log_act("user", res.meta.last_row_id, uid, "CREATED", "Added " + name + " as " + role).run()
                return ok({"id": res.meta.last_row_id})

            if path == "/api/admin/users/update" and method == "POST":
                target = body.get("id")
                if target == uid:
                    return fail("You can't change your own account here")
                rows = await self.q("SELECT name, role, active FROM users WHERE id = ?", target)
                if not rows:
                    return fail("Not found", 404)
                role = body.get("role", rows[0]["role"])
                active = 1 if body.get("active", rows[0]["active"]) else 0
                if role not in ("employee", "manager"):
                    return fail("Invalid role")
                stmts = [
                    self.st("UPDATE users SET role = ?, active = ? WHERE id = ?", role, active, target),
                    self.log_act("user", target, uid, "UPDATED",
                                 rows[0]["name"] + ": role=" + role + ", active=" + str(active)),
                ]
                if not active:
                    stmts.append(self.st("UPDATE work_offers SET status = 'cancelled' "
                                         "WHERE user_id = ? AND status = 'open'", target))
                await db.batch(to_js(stmts))
                return ok()

            if path == "/api/admin/shifts" and method == "GET":
                frm = (qs.get("from") or [str(_date.today())])[0]
                to = (qs.get("to") or [str(_date.today() + timedelta(days=13))])[0]
                if not DATE_RE.match(frm) or not DATE_RE.match(to):
                    return fail("Invalid dates")
                return ok(await self.q("""
                    SELECT s.id, s.user_id, s.shift_date, s.start_time, s.end_time, u.name AS user_name,
                           EXISTS (SELECT 1 FROM shift_requests sr
                                   WHERE (sr.original_shift_id = s.id OR sr.trade_shift_id = s.id)
                                     AND sr.status IN ('open', 'claimed')) AS locked
                    FROM shifts s JOIN users u ON u.id = s.user_id
                    WHERE s.shift_date BETWEEN ? AND ?
                    ORDER BY s.shift_date, s.start_time, u.name LIMIT 300""", frm, to))

            if path == "/api/admin/shifts" and method == "POST":
                who, d = body.get("userId"), body.get("date") or ""
                start, end = body.get("start") or "", body.get("end") or ""
                if not DATE_RE.match(d) or not valid_range(start, end):
                    return fail("Check the date and times")
                if not await self.q("SELECT id FROM users WHERE id = ? AND active = 1", who):
                    return fail("Pick an active employee")
                if await self.has_conflict(who, d, start, end):
                    return fail("That person already works during that time", 409)
                res = await self.st(
                    "INSERT INTO shifts (user_id, shift_date, start_time, end_time, status) VALUES (?, ?, ?, ?, ?)",
                    who, d, start, end, SHIFT_STATUS).run()
                await self.log_act("shift", res.meta.last_row_id, uid, "CREATED",
                                   "Shift " + d + " " + start + "-" + end + " for user #" + str(who)).run()
                return ok({"id": res.meta.last_row_id})

            if path == "/api/admin/shifts/update" and method == "POST":
                sid = body.get("id")
                rows = await self.q("SELECT user_id, shift_date, start_time, end_time FROM shifts WHERE id = ?", sid)
                if not rows:
                    return fail("Not found", 404)
                cur = rows[0]
                if await self.active_request(sid):
                    return fail("This shift has an open request; cancel it first", 409)
                who = body.get("userId", cur["user_id"])
                d = body.get("date", cur["shift_date"])
                start, end = body.get("start", cur["start_time"]), body.get("end", cur["end_time"])
                if not DATE_RE.match(d or "") or not valid_range(start, end):
                    return fail("Check the date and times")
                if not await self.q("SELECT id FROM users WHERE id = ? AND active = 1", who):
                    return fail("Pick an active employee")
                if await self.has_conflict(who, d, start, end, sid):
                    return fail("That person already works during that time", 409)
                await db.batch(to_js([
                    self.st("UPDATE shifts SET user_id = ?, shift_date = ?, start_time = ?, end_time = ? WHERE id = ?",
                            who, d, start, end, sid),
                    self.log_act("shift", sid, uid, "UPDATED",
                                 "Now user #" + str(who) + " " + d + " " + start + "-" + end),
                ]))
                return ok()

            if path == "/api/admin/shifts/delete" and method == "POST":
                sid = body.get("id")
                if await self.q("SELECT id FROM shift_requests WHERE original_shift_id = ? OR trade_shift_id = ? LIMIT 1",
                                sid, sid):
                    return fail("This shift has swap history; reassign it instead of deleting", 409)
                res = await self.st("DELETE FROM shifts WHERE id = ?", sid).run()
                if changes(res) == 0:
                    return fail("Not found", 404)
                await self.log_act("shift", sid, uid, "DELETED", "Shift deleted").run()
                return ok()

            return fail("Not found", 404)

        # ===== Reports & audit (managers) =====
        if path in ("/api/report", "/api/report.csv", "/api/audit-logs") and method == "GET":
            if not is_mgr:
                return fail("Managers only", 403)

            if path == "/api/audit-logs":
                return ok(await self.q("""
                    SELECT x.kind, x.ref, x.action_taken, x.log_notes, x.timestamp, u.name AS actor_name
                    FROM (
                      SELECT 'swap' AS kind, request_id AS ref, action_by, action_taken, log_notes, timestamp
                        FROM shift_audit_logs
                      UNION ALL
                      SELECT ref_type, ref_id, action_by, action_taken, log_notes, timestamp FROM activity_log
                    ) x LEFT JOIN users u ON u.id = x.action_by
                    ORDER BY x.timestamp DESC LIMIT 150"""))

            frm = (qs.get("from") or ["1970-01-01"])[0]
            to = (qs.get("to") or ["9999-12-31"])[0]
            if not DATE_RE.match(frm) or not DATE_RE.match(to):
                return fail("Invalid dates")
            report = await self.build_report(frm, to)

            if path == "/api/report":
                return ok(report)

            lines = [",".join(csv_cell(h) for h in
                              ["Type", "Date", "Start", "End", "Gave up by", "Taken by", "Approved by",
                               "Approved at", "Traded for date", "Traded for start", "Traded for end"])]
            for x in report["rows"]:
                lines.append(",".join(csv_cell(x.get(k)) for k in
                                      ["kind", "shift_date", "start_time", "end_time", "gave", "took",
                                       "approved_by", "approved_at", "other_date", "other_start", "other_end"]))
            headers = dict(SEC)
            headers["Content-Type"] = "text/csv; charset=utf-8"
            headers["Content-Disposition"] = "attachment; filename=shift-report.csv"
            headers["Cache-Control"] = "no-store"
            return Response("\r\n".join(lines), headers=headers)

        return fail("Not found", 404)

from workers import WorkerEntrypoint, Response
from pyodide.ffi import to_js
import json
from urllib.parse import urlparse

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shift Exchange Portal</title>
<style>
  body { font-family: -apple-system, sans-serif; padding: 16px; background: #f4f6f8; color: #333; max-width: 640px; margin: 0 auto; }
  .card { background: #fff; padding: 14px; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,.05); }
  .row { border-bottom: 1px solid #eee; padding: 8px 0; }
  .row:last-child { border-bottom: none; }
  .btn { border: none; padding: 10px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; background: #0070f3; color: #fff; margin: 6px 6px 0 0; }
  .btn.red { background: #d93025; }
  select { width: 100%; padding: 10px; font-size: 16px; }
  .tag { font-size: 12px; background: #eef; padding: 2px 8px; border-radius: 10px; }
  .muted { color: #777; font-size: 13px; }
  #err { color: #d93025; margin-bottom: 8px; }
</style>
</head>
<body>
<h2>Shift Exchange Portal</h2>
<div class="card"><label>Signed in as</label><select id="userSel"></select></div>
<div id="err"></div>

<div class="card"><h3>Open requests</h3><div id="open"></div></div>
<div class="card"><h3>My shifts</h3><div id="mine"></div></div>
<div class="card" id="mgrCard" style="display:none"><h3>Pending approval</h3><div id="pending"></div></div>
<div class="card" id="logCard" style="display:none"><h3>Audit log</h3><div id="logs"></div></div>

<script>
let users = [], me = null;

function esc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({'Content-Type': 'application/json'}, opts.headers || {});
  if (me) opts.headers['X-User-Id'] = String(me.id);
  const res = await fetch(path, opts);
  const json = await res.json();
  if (!json.success) { document.getElementById('err').textContent = json.error || 'Error'; throw new Error(json.error); }
  document.getElementById('err').textContent = '';
  return json.data;
}

function post(path, body) { return api(path, {method: 'POST', body: JSON.stringify(body)}).then(refresh).catch(() => {}); }

async function init() {
  users = await api('/api/users');
  const sel = document.getElementById('userSel');
  sel.innerHTML = users.map(u => '<option value="' + u.id + '">' + esc(u.name) + ' (' + esc(u.role) + ')</option>').join('');
  const saved = parseInt(localStorage.getItem('uid'));
  me = users.find(u => u.id === saved) || users[0];
  sel.value = me.id;
  sel.onchange = () => { me = users.find(u => u.id === parseInt(sel.value)); localStorage.setItem('uid', me.id); refresh(); };
  refresh();
}

async function refresh() {
  const isMgr = me.role === 'manager';
  document.getElementById('mgrCard').style.display = isMgr ? '' : 'none';
  document.getElementById('logCard').style.display = isMgr ? '' : 'none';

  const reqs = await api('/api/requests');
  const open = reqs.filter(r => r.status === 'open');
  document.getElementById('open').innerHTML = open.length ? open.map(r =>
    '<div class="row"><b>' + esc(r.shift_date) + '</b> ' + esc(r.start_time) + '-' + esc(r.end_time) +
    '<div class="muted">From ' + esc(r.requester_name) + '</div>' +
    (r.requester_id !== me.id ? '<button class="btn" onclick="post(\\'/api/claim\\',{requestId:' + r.id + '})">Claim</button>' : '<span class="tag">Your request</span>') +
    '</div>').join('') : '<p class="muted">No open requests.</p>';

  const mine = await api('/api/my-shifts');
  document.getElementById('mine').innerHTML = mine.length ? mine.map(s =>
    '<div class="row"><b>' + esc(s.shift_date) + '</b> ' + esc(s.start_time) + '-' + esc(s.end_time) +
    '<br><button class="btn" onclick="post(\\'/api/create-request\\',{shiftId:' + s.id + '})">Offer up</button></div>').join('')
    : '<p class="muted">No shifts.</p>';

  if (isMgr) {
    const pend = reqs.filter(r => r.status === 'claimed');
    document.getElementById('pending').innerHTML = pend.length ? pend.map(r =>
      '<div class="row"><b>' + esc(r.shift_date) + '</b> ' + esc(r.start_time) + '-' + esc(r.end_time) +
      '<div class="muted">' + esc(r.requester_name) + ' &rarr; ' + esc(r.claiming_name) + '</div>' +
      '<button class="btn" onclick="post(\\'/api/approve\\',{requestId:' + r.id + ',decision:\\'approve\\'})">Approve</button>' +
      '<button class="btn red" onclick="post(\\'/api/approve\\',{requestId:' + r.id + ',decision:\\'reject\\'})">Reject</button></div>').join('')
      : '<p class="muted">Nothing pending.</p>';

    const logs = await api('/api/audit-logs');
    document.getElementById('logs').innerHTML = logs.map(l =>
      '<div class="row muted">#' + l.request_id + ' ' + esc(l.action_taken) + ' by ' + esc(l.actor_name) +
      '<br>' + esc(l.log_notes) + ' &middot; ' + esc(l.timestamp) + '</div>').join('') || '<p class="muted">No logs.</p>';
  }
}
init();
</script>
</body>
</html>
"""


def jres(payload, status=200):
    return Response(json.dumps(payload), status=status,
                    headers={"Content-Type": "application/json"})


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


class Default(WorkerEntrypoint):
    async def query(self, sql, *params):
        res = await self.env.DB.prepare(sql).bind(*params).all()
        return to_rows(res)

    async def current_user(self, request):
        """Identify the caller.
        1) Cloudflare Access email header (secure, when Access protects the app)
        2) X-User-Id header (DEMO ONLY - spoofable; remove once Access is on)
        """
        email = request.headers.get("Cf-Access-Authenticated-User-Email")
        if email:
            rows = await self.query("SELECT id, name, email, role FROM users WHERE email = ?", email)
        else:
            try:
                uid = int(request.headers.get("X-User-Id") or 0)
            except ValueError:
                uid = 0
            if not uid:
                return None
            rows = await self.query("SELECT id, name, email, role FROM users WHERE id = ?", uid)
        return rows[0] if rows else None

    async def fetch(self, request):
        path = urlparse(request.url).path
        method = request.method
        db = self.env.DB

        if path == "/" and method == "GET":
            return Response(HTML, headers={"Content-Type": "text/html;charset=UTF-8"})

        if not path.startswith("/api/"):
            return Response("Not Found", status=404)

        # Public list for the user picker (demo mode). Remove when using Access.
        if path == "/api/users" and method == "GET":
            return ok(await self.query("SELECT id, name, role FROM users ORDER BY name"))

        user = await self.current_user(request)
        if not user:
            return fail("Not signed in", 401)

        body = {}
        if method == "POST":
            try:
                body = await request.json()
                if hasattr(body, "to_py"):
                    body = body.to_py()
            except Exception:
                return fail("Invalid JSON")

        # --- List requests ---
        if path == "/api/requests" and method == "GET":
            rows = await self.query("""
                SELECT sr.id, sr.status, sr.requester_id, sr.claiming_user_id,
                       s.shift_date, s.start_time, s.end_time,
                       u1.name AS requester_name, u2.name AS claiming_name
                FROM shift_requests sr
                JOIN shifts s ON sr.original_shift_id = s.id
                JOIN users u1 ON sr.requester_id = u1.id
                LEFT JOIN users u2 ON sr.claiming_user_id = u2.id
                ORDER BY sr.id DESC
            """)
            return ok(rows)

        # --- My shifts ---
        if path == "/api/my-shifts" and method == "GET":
            rows = await self.query("""
                SELECT s.id, s.shift_date, s.start_time, s.end_time
                FROM shifts s
                WHERE s.user_id = ?
                  AND s.id NOT IN (SELECT original_shift_id FROM shift_requests
                                   WHERE status IN ('open','claimed'))
                ORDER BY s.shift_date, s.start_time
            """, user["id"])
            return ok(rows)

        # --- Create request ---
        if path == "/api/create-request" and method == "POST":
            shift_id = body.get("shiftId")
            shifts = await self.query("SELECT id FROM shifts WHERE id = ? AND user_id = ?", shift_id, user["id"])
            if not shifts:
                return fail("You can only offer your own shifts", 403)
            dup = await self.query(
                "SELECT id FROM shift_requests WHERE original_shift_id = ? AND status IN ('open','claimed')", shift_id)
            if dup:
                return fail("This shift already has an active request", 409)

            res = await db.prepare(
                "INSERT INTO shift_requests (request_type, original_shift_id, requester_id, status) "
                "VALUES ('giveaway', ?, ?, 'open')"
            ).bind(shift_id, user["id"]).run()
            new_id = res.meta.last_row_id
            await db.prepare(
                "INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) "
                "VALUES (?, ?, 'CREATED', 'Employee offered shift')"
            ).bind(new_id, user["id"]).run()
            return ok({"id": new_id})

        # --- Claim ---
        if path == "/api/claim" and method == "POST":
            req_id = body.get("requestId")
            res = await db.prepare(
                "UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed', "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND status = 'open' AND requester_id != ?"
            ).bind(user["id"], req_id, user["id"]).run()
            if changes(res) == 0:
                return fail("Request is not open, or it is your own", 409)
            await db.prepare(
                "INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) "
                "VALUES (?, ?, 'CLAIMED', 'Employee claimed shift')"
            ).bind(req_id, user["id"]).run()
            return ok()

        # --- Approve / reject (managers only) ---
        if path == "/api/approve" and method == "POST":
            if user["role"] != "manager":
                return fail("Managers only", 403)
            req_id = body.get("requestId")
            decision = body.get("decision")
            if decision not in ("approve", "reject"):
                return fail("decision must be 'approve' or 'reject'")

            rows = await self.query(
                "SELECT original_shift_id, claiming_user_id FROM shift_requests "
                "WHERE id = ? AND status = 'claimed'", req_id)
            if not rows:
                return fail("Request is not awaiting approval", 409)
            r = rows[0]

            if decision == "approve":
                stmts = [
                    db.prepare("UPDATE shifts SET user_id = ? WHERE id = ?")
                      .bind(r["claiming_user_id"], r["original_shift_id"]),
                    db.prepare("UPDATE shift_requests SET status = 'approved', manager_id = ?, "
                               "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'claimed'")
                      .bind(user["id"], req_id),
                    db.prepare("INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) "
                               "VALUES (?, ?, 'APPROVED', 'Manager approved swap')")
                      .bind(req_id, user["id"]),
                ]
            else:
                stmts = [
                    db.prepare("UPDATE shift_requests SET status = 'rejected', manager_id = ?, "
                               "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'claimed'")
                      .bind(user["id"], req_id),
                    db.prepare("INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) "
                               "VALUES (?, ?, 'REJECTED', 'Manager rejected swap')")
                      .bind(req_id, user["id"]),
                ]
            await db.batch(to_js(stmts))  # one atomic transaction
            return ok()

        # --- Audit logs (managers only) ---
        if path == "/api/audit-logs" and method == "GET":
            if user["role"] != "manager":
                return fail("Managers only", 403)
            rows = await self.query("""
                SELECT l.id, l.request_id, l.action_taken, l.log_notes, l.timestamp,
                       u.name AS actor_name
                FROM shift_audit_logs l
                LEFT JOIN users u ON l.action_by = u.id
                ORDER BY l.id DESC LIMIT 100
            """)
            return ok(rows)

        return fail("Not found", 404)

import { Hono } from 'hono';

const app = new Hono();

app.get('/', (c) => {
  return c.html(`
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Shift Exchange Portal</title>
      <style>
        body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 15px; background: #f4f6f8; color: #333; }
        .card { background: white; padding: 15px; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .btn { border: none; padding: 10px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-right: 5px; }
        .btn-primary { background: #0070f3; color: white; }
        .btn-success { background: #10b981; color: white; }
        .btn-danger { background: #ef4444; color: white; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; background: #e5e7eb; }
        .badge-open { background: #fef3c7; color: #92400e; }
        .badge-claimed { background: #dbeafe; color: #1e40af; }
        .badge-approved { background: #d1fae5; color: #065f46; }
        .badge-rejected { background: #fee2e2; color: #991b1b; }
      </style>
    </head>
    <body>
      <h2>Shift Exchange Portal</h2>
      
      <div class="card">
        <h3>Available & Requested Shifts</h3>
        <div id="shiftsList">Loading shifts...</div>
      </div>

      <div class="card">
        <h3>Manager Audit Report</h3>
        <div id="auditReport">Loading logs...</div>
      </div>

      <script>
        async function loadShifts() {
          try {
            const res = await fetch('/api/requests');
            const json = await res.json();
            const container = document.getElementById('shiftsList');
            
            if (!json.data || json.data.length === 0) {
              container.innerHTML = '<p>No open shift requests.</p>';
              return;
            }

            let html = '';
            for (let req of json.data) {
              let claimingHtml = req.claiming_name ? '<div><strong>Claimed By:</strong> ' + req.claiming_name + '</div>' : '';
              let actionHtml = '';
              
              if (req.status === 'open') {
                actionHtml = '<button class="btn btn-primary" onclick="claimShift(' + req.id + ')">Claim Shift</button>';
              } else if (req.status === 'claimed') {
                actionHtml = '<button class="btn btn-success" onclick="approveShift(' + req.id + ', \'APPROVED\')">Manager Approve</button>' +
                             '<button class="btn btn-danger" onclick="approveShift(' + req.id + ', \'REJECTED\')">Reject</button>';
              }

              html += '<div style="border-bottom: 1px solid #eee; padding-bottom: 8px; margin-bottom: 8px;">' +
                      '<div><strong>Shift Date:</strong> ' + req.shift_date + ' (' + req.start_time + ' - ' + req.end_time + ')</div>' +
                      '<div><strong>Requested By:</strong> ' + req.requester_name + '</div>' +
                      '<div><strong>Status:</strong> <span class="badge badge-' + req.status + '">' + req.status.toUpperCase() + '</span></div>' +
                      claimingHtml +
                      '<div style="margin-top: 8px;">' + actionHtml + '</div>' +
                      '</div>';
            }
            container.innerHTML = html;
          } catch(e) {
            document.getElementById('shiftsList').innerHTML = '<p>Error loading shifts.</p>';
          }
        }

        async function loadAuditLogs() {
          try {
            const res = await fetch('/api/audit-logs');
            const json = await res.json();
            const container = document.getElementById('auditReport');
            
            if (!json.data || json.data.length === 0) {
              container.innerHTML = '<p>No audit records found.</p>';
              return;
            }

            let html = '<ul>';
            for (let log of json.data) {
              html += '<li><strong>' + log.action_taken + '</strong> by ' + log.actor_name + ' on Request #' + log.request_id + '<br><small>' + new Date(log.timestamp).toLocaleString() + '</small></li>';
            }
            html += '</ul>';
            container.innerHTML = html;
          } catch(e) {
            document.getElementById('auditReport').innerHTML = '<p>Error loading logs.</p>';
          }
        }

        async function claimShift(requestId) {
          const userId = prompt("Enter your User ID to claim this shift (Try 2 or 3):");
          if (!userId) return;

          await fetch('/api/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requestId, claimingUserId: parseInt(userId) })
          });
          loadShifts();
          loadAuditLogs();
        }

        async function approveShift(requestId, status) {
          const managerId = prompt("Enter Manager ID to finalize decision (Try 1):");
          if (!managerId) return;

          await fetch('/api/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requestId, managerId: parseInt(managerId), status })
          });
          loadShifts();
          loadAuditLogs();
        }

        loadShifts();
        loadAuditLogs();
      </script>
    </body>
    </html>
  `);
});

app.get('/api/requests', async (c) => {
  const query = "SELECT sr.id, sr.status, s.shift_date, s.start_time, s.end_time, u1.name as requester_name, u2.name as claiming_name FROM shift_requests sr JOIN shifts s ON sr.original_shift_id = s.id JOIN users u1 ON sr.requester_id = u1.id LEFT JOIN users u2 ON sr.claiming_user_id = u2.id ORDER BY sr.id DESC";
  const { results } = await c.env.DB.prepare(query).all();
  return c.json({ success: true, data: results });
});

app.post('/api/claim', async (c) => {
  const { requestId, claimingUserId } = await c.req.json();
  await c.env.DB.prepare("UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'open'").bind(claimingUserId, requestId).run();
  await c.env.DB.prepare("INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) VALUES (?, ?, 'CLAIMED', 'Employee claimed shift')").bind(requestId, claimingUserId).run();
  return c.json({ success: true });
});

app.post('/api/approve', async (c) => {
  const { requestId, managerId, status } = await c.req.json();
  await c.env.DB.prepare("UPDATE shift_requests SET manager_id = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?").bind(managerId, status.toLowerCase(), requestId).run();
  await c.env.DB.prepare("INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) VALUES (?, ?, ?, 'Manager decision')").bind(requestId, managerId, status).run();
  return c.json({ success: true });
});

app.get('/api/audit-logs', async (c) => {
  const query = "SELECT l.id, l.request_id, l.action_taken, l.timestamp, u.name as actor_name FROM shift_audit_logs l JOIN users u ON l.action_by = u.id ORDER BY l.timestamp DESC LIMIT 100";
  const { results } = await c.env.DB.prepare(query).all();
  return c.json({ success: true, data: results });
});

export default app;

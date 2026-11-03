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
        body { font-family: sans-serif; padding: 20px; background: #f4f6f8; }
        .card { background: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        button { padding: 8px 12px; background: #0070f3; color: white; border: none; border-radius: 4px; cursor: pointer; }
      </style>
    </head>
    <body>
      <h2>Shift Exchange Portal</h2>
      <div class="card">
        <h3>Shifts</h3>
        <div id="content">Loading from API...</div>
      </div>

      <script>
        async function init() {
          try {
            const res = await fetch('/api/requests');
            const json = await res.json();
            
            if (!json.success || !json.data || json.data.length === 0) {
              document.getElementById('content').innerHTML = '<p>No shifts found in database.</p>';
              return;
            }

            let html = '';
            json.data.forEach(req => {
              html += \`
                <div style="border-bottom: 1px solid #ddd; padding: 8px 0;">
                  <strong>Date:</strong> \$_esc(req.shift_date) (\$_esc(req.start_time))<br>
                  <strong>Requester:</strong> \$_esc(req.requester_name)<br>
                  <strong>Status:</strong> \$_esc(req.status)<br>
                  <button onclick="claim(\${req.id})">Claim Shift</button>
                </div>
              \`.replace(/\\$_esc\\(/g, ''); // simple template cleanup
            });
            document.getElementById('content').innerHTML = html;
          } catch (err) {
            document.getElementById('content').innerHTML = '<p style="color:red;">Error: ' + err.message + '</p>';
          }
        }

        async function claim(id) {
          const uid = prompt("Enter your User ID (e.g. 2 or 3):");
          if (!uid) return;
          await fetch('/api/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requestId: id, claimingUserId: parseInt(uid) })
          });
          alert('Claim submitted!');
          init();
        }

        init();
      </script>
    </body>
    </html>
  `);
});

app.get('/api/requests', async (c) => {
  try {
    const query = "SELECT sr.id, sr.status, s.shift_date, s.start_time, s.end_time, u1.name as requester_name, u2.name as claiming_name FROM shift_requests sr JOIN shifts s ON sr.original_shift_id = s.id JOIN users u1 ON sr.requester_id = u1.id LEFT JOIN users u2 ON sr.claiming_user_id = u2.id ORDER BY sr.id DESC";
    const { results } = await c.env.DB.prepare(query).all();
    return c.json({ success: true, data: results });
  } catch (e) {
    return c.json({ success: false, error: e.message }, 500);
  }
});

app.post('/api/claim', async (c) => {
  try {
    const { requestId, claimingUserId } = await c.req.json();
    await c.env.DB.prepare("UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'open'").bind(claimingUserId, requestId).run();
    await c.env.DB.prepare("INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) VALUES (?, ?, 'CLAIMED', 'Employee claimed shift')").bind(requestId, claimingUserId).run();
    return c.json({ success: true });
  } catch (e) {
    return c.json({ success: false, error: e.message }, 500);
  }
});

export default app;

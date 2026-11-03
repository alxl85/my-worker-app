from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from workers import asgi

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Shift Exchange Portal (Python)</title>
      <style>
        body { font-family: -apple-system, sans-serif; padding: 20px; background: #f4f6f8; color: #333; }
        .card { background: white; padding: 15px; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .btn { border: none; padding: 8px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; background: #0070f3; color: white; }
      </style>
    </head>
    <body>
      <h2>Shift Exchange Portal (Python)</h2>
      <div class="card">
        <h3>Available Shifts</h3>
        <div id="shiftsList">Loading shifts...</div>
      </div>
      <script>
        async function loadShifts() {
          const res = await fetch('/api/requests');
          const json = await res.json();
          const container = document.getElementById('shiftsList');
          
          if (!json.data || json.data.length === 0) {
            container.innerHTML = '<p>No open shift requests.</p>';
            return;
          }

          let html = '';
          json.data.forEach(req => {
            html += `
              <div style="border-bottom: 1px solid #eee; padding-bottom: 8px; margin-bottom: 8px;">
                <div><strong>Date:</strong> \${req.shift_date} (\${req.start_time} - \${req.end_time})</div>
                <div><strong>Requester:</strong> \${req.requester_name}</div>
                <div><strong>Status:</strong> \${req.status.toUpperCase()}</div>
                <div style="margin-top: 8px;">
                  <button class="btn" onclick="claimShift(\${req.id})">Claim Shift</button>
                </div>
              </div>
            `;
          });
          container.innerHTML = html;
        }

        async function claimShift(requestId) {
          const userId = prompt("Enter your User ID to claim (e.g. 2 or 3):");
          if (!userId) return;

          await fetch('/api/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requestId: requestId, claimingUserId: parseInt(userId) })
          });
          loadShifts();
        }

        loadShifts();
      </script>
    </body>
    </html>
    """

@app.get("/api/requests")
async def get_requests(request: Request):
    db = request.scope["env"].DB
    query = """
        SELECT sr.id, sr.status, s.shift_date, s.start_time, s.end_time,
               u1.name as requester_name, u2.name as claiming_name
        FROM shift_requests sr
        JOIN shifts s ON sr.original_shift_id = s.id
        JOIN users u1 ON sr.requester_id = u1.id
        LEFT JOIN users u2 ON sr.claiming_user_id = u2.id
        ORDER BY sr.id DESC
    """
    results = await db.prepare(query).all()
    return {"success": True, "data": results.to_py()}

@app.post("/api/claim")
async def claim_shift(request: Request):
    db = request.scope["env"].DB
    body = await request.json()
    req_id = body.get("requestId")
    user_id = body.get("claimingUserId")

    await db.prepare(
        "UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'open'"
    ).bind(user_id, req_id).run()

    await db.prepare(
        "INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) VALUES (?, ?, 'CLAIMED', 'Employee claimed shift')"
    ).bind(req_id, user_id).run()

    return {"success": True}

# Cloudflare ASGI bridge
to_asgi = asgi.entrypoint(app)


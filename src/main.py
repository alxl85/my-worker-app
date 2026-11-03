from workers import WorkerEntrypoint, Response
import json
from urllib.parse import urlparse

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = urlparse(request.url)
        path = url.path
        method = request.method
        db = self.env.DB
        
        # 1. Main HTML Interface
        if path == "/" and method == "GET":
            html_content = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Shift Exchange Portal</title>
              <style>
                body { font-family: -apple-system, sans-serif; padding: 20px; background: #f4f6f8; color: #333; }
                .card { background: white; padding: 15px; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
                .btn { border: none; padding: 8px 14px; border-radius: 6px; font-weight: bold; cursor: pointer; background: #0070f3; color: white; }
              </style>
            </head>
            <body>
              <h2>Shift Exchange Portal</h2>
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
                    html += '<div style="border-bottom: 1px solid #eee; padding-bottom: 8px; margin-bottom: 8px;">' +
                            '<div><strong>Date:</strong> ' + req.shift_date + ' (' + req.start_time + ' - ' + req.end_time + ')</div>' +
                            '<div><strong>Requester:</strong> ' + req.requester_name + '</div>' +
                            '<div><strong>Status:</strong> ' + req.status.toUpperCase() + '</div>' +
                            '<div style="margin-top: 8px;"><button class="btn" onclick="claimShift(' + req.id + ')">Claim Shift</button></div>' +
                            '</div>';
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
            return Response(html_content, headers={"Content-Type": "text/html;charset=UTF-8"})

        # 2. API: Fetch Shifts
        elif path == "/api/requests" and method == "GET":
            query = """
                SELECT sr.id, sr.status, s.shift_date, s.start_time, s.end_time,
                       u1.name as requester_name, u2.name as claiming_name
                FROM shift_requests sr
                JOIN shifts s ON sr.original_shift_id = s.id
                JOIN users u1 ON sr.requester_id = u1.id
                LEFT JOIN users u2 ON sr.claiming_user_id = u2.id
                ORDER BY sr.id DESC
            """
            result = await db.prepare(query).all()
            rows = result.results if hasattr(result, "results") else list(result)
            return Response(json.dumps({"success": True, "data": rows}), headers={"Content-Type": "application/json"})

        # 3. API: Claim Shift
        elif path == "/api/claim" and method == "POST":
            body = await request.json()
            req_id = body.get("requestId")
            user_id = body.get("claimingUserId")

            await db.prepare(
                "UPDATE shift_requests SET claiming_user_id = ?, status = 'claimed', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'open'"
            ).bind(user_id, req_id).run()

            await db.prepare(
                "INSERT INTO shift_audit_logs (request_id, action_by, action_taken, log_notes) VALUES (?, ?, 'CLAIMED', 'Employee claimed shift')"
            ).bind(req_id, user_id).run()

            return Response(json.dumps({"success": True}), headers={"Content-Type": "application/json"})

        return Response("Not Found", status=404)

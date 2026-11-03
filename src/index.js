
import { Hono } from 'hono';

const app = new Hono();

// Frontend UI served directly to Chrome and mobile browsers
app.get('/', (c) => {
  return c.html(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>App Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; color: #333; }
          h2 { color: #f48120; }
          input { width: 70%; padding: 12px; font-size: 16px; border: 1px solid #ccc; border-radius: 4px; margin-right: 8px; }
          button { padding: 12px 20px; font-size: 16px; background-color: #f48120; color: white; border: none; border-radius: 4px; cursor: pointer; }
          button:active { background-color: #d66c15; }
          ul { margin-top: 25px; padding-left: 0; list-style: none; }
          li { background: #f9f9f9; padding: 12px; margin-bottom: 8px; border-radius: 4px; border: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
          small { color: #888; }
        </style>
      </head>
      <body>
        <h2>Multi-Client Dashboard</h2>
        <div style="display: flex;">
          <input type="text" id="val" placeholder="Type a entry..." />
          <button onclick="sendData()">Submit</button>
        </div>
        <ul id="list">Loading...</ul>

        <script>
          async function loadData() {
            try {
              const res = await fetch('/api/records');
              const json = await res.json();
              const list = document.getElementById('list');
              if(!json.data || json.data.length === 0) {
                list.innerHTML = '<li><small>No records found yet.</small></li>';
                return;
              }
              list.innerHTML = json.data.map(r => \`<li><span>\${r.value}</span> <small>\${new Date(r.created_at).toLocaleTimeString()}</small></li>\`).join('');
            } catch (e) {
              document.getElementById('list').innerHTML = '<li>Error loading data</li>';
            }
          }

          async function sendData() {
            const input = document.getElementById('val');
            const val = input.value.trim();
            if(!val) return;

            await fetch('/api/records', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ value: val })
            });

            input.value = '';
            loadData();
          }

          loadData();
        </script>
      </body>
    </html>
  `);
});

// API Route: Get records
app.get('/api/records', async (c) => {
  try {
    const { results } = await c.env.DB.prepare("SELECT * FROM records ORDER BY id DESC LIMIT 50").all();
    return c.json({ success: true, data: results });
  } catch (e) {
    return c.json({ success: false, error: e.message }, 500);
  }
});

// API Route: Insert record
app.post('/api/records', async (c) => {
  try {
    const body = await c.req.json();
    const { value } = body;
    if (!value) return c.json({ success: false, error: "Empty value" }, 400);

    const result = await c.env.DB.prepare("INSERT INTO records (value) VALUES (?)").bind(value).run();
    return c.json({ success: true, result });
  } catch (e) {
    return c.json({ success: false, error: e.message }, 500);
  }
});

export default app;

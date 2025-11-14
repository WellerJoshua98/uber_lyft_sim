from flask import Blueprint, render_template_string, request

driver_home = Blueprint("driver_home", __name__)

# --- Mock data (UI-only demo) ---
def get_mock_requests():
    # In real app, fetch from DB/queue. Here we just return some examples.
    return [
        {"id": "rq-101", "pickup": "350 5th Ave, New York, NY", "destination": "Times Square, New York, NY", "fare": 14.80, "eta": "Now"},
        {"id": "rq-102", "pickup": "1 Liberty Island, NY", "destination": "Brooklyn Bridge, NY", "fare": 22.10, "eta": "1 min"},
        {"id": "rq-103", "pickup": "JFK Terminal 4", "destination": "Midtown Manhattan", "fare": 45.30, "eta": "3 mins"}
    ]

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Driver Homepage</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css" rel="stylesheet">
  <style>
    body { padding: 1rem; }
    .muted { color:#666; font-size:.95rem; }
    .grid { display: grid; gap: 1rem; }
    @media (min-width: 900px) { .grid { grid-template-columns: repeat(2, 1fr); } }
    .card {
      border: 1px solid #e5e7eb; border-radius: 12px; padding: 1rem; background: #fff;
      box-shadow: 0 1px 2px rgba(0,0,0,.04);
    }
    .row { display:flex; align-items:center; justify-content:space-between; gap:.75rem; }
    .pill { padding:.2rem .6rem; border-radius:999px; background:#eef; font-size:.85rem; }
    .actions { display:flex; gap:.5rem; flex-wrap:wrap; }
    nav a { margin-right:.5rem; }
  </style>
</head>
<body>
  <main class="container">
    {{ body|safe }}
  </main>
</body>
</html>
"""


HOME_BODY = """
<h2>Driver Homepage</h2>
<p class="muted">Incoming ride requests. Accept or decline. (UI only — no backend logic yet.)</p>

{% if banner %}
  <article class="contrast">
    <strong>{{ banner.title }}</strong>
    <p class="muted">{{ banner.detail }}</p>
  </article>
{% endif %}

<section class="grid">
  {% for r in requests %}
  <article class="card">
    <div class="row">
      <h3 style="margin:0">Request {{ r.id }}</h3>
      <span class="pill">Est. Fare: ${{ '%.2f'|format(r.fare) }}</span>
    </div>
    <p style="margin:.5rem 0 0 0"><strong>Pickup:</strong> {{ r.pickup }}</p>
    <p style="margin:.25rem 0 .5rem 0"><strong>Destination:</strong> {{ r.destination }}</p>
    <p class="muted" style="margin:0">ETA to pickup: {{ r.eta }}</p>

    <form method="POST" action="{{ url_for('driver_home.home') }}" style="margin-top:.75rem">
      <input type="hidden" name="request_id" value="{{ r.id }}">
      <div class="actions">
        <button type="submit" name="decision" value="accept">Accept</button>
        <button type="submit" name="decision" value="decline" class="secondary">Decline</button>
      </div>
    </form>
  </article>
  {% endfor %}
</section>
"""

@driver_home.route("/", methods=["GET", "POST"])
def home():
    banner = None
    if request.method == "POST":
        req_id = (request.form.get("request_id") or "").strip()
        decision = (request.form.get("decision") or "").strip()
        if req_id and decision in {"accept", "decline"}:
            verb = "accepted" if decision == "accept" else "declined"
            banner = {
                "title": f"Request {req_id} {verb}.",
                "detail": ""
            }
    
    body = render_template_string(
        HOME_BODY,
        requests=get_mock_requests(),
        banner = banner
    )
    return render_template_string(BASE_HTML, body=body)
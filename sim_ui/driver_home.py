## Coded with help from chat gpt
from flask import Blueprint, render_template_string, request
import folium
import db

driver_home = Blueprint("driver_home", __name__)

# --------- Map helper for driver view ---------
def make_driver_map():
    # Static center for now; swap with real nav later
    fmap = folium.Map(location=[40.758, -73.9855], zoom_start=12, tiles="OpenStreetMap")
    return fmap._repr_html_()

# --- Mock data (UI-only demo) ---
def get_mock_requests():
    # In real app, fetch from DB/queue. Here we just return some examples.
    return [
        {"id": "rq-101", "pickup": "350 5th Ave, New York, NY", "destination": "Times Square, New York, NY", "fare": 14.80, "eta": "Now"},
        {"id": "rq-102", "pickup": "1 Liberty Island, NY", "destination": "Brooklyn Bridge, NY", "fare": 22.10, "eta": "1 min"},
        {"id": "rq-103", "pickup": "JFK Terminal 4", "destination": "Midtown Manhattan", "fare": 45.30, "eta": "3 mins"}
    ]


# Status label mapping for UI
TRIP_STATUS_LABELS = {
    "requested": "Requested",
    "accepted": "Accepted",
    "to_pickup": "To Pickup",
    "to_destination": "To Destination",
    "completed": "Complete",
    "declined": "Declined",
}

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
<nav>
  <a href="{{ url_for('driver_home.home') }}"><strong>Driver Home</strong></a>
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Rider Home</a>
</nav>

<h2>Driver Homepage</h2>
<p class="muted">Incoming ride requests. Accept or decline.</p>

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
      <h3 style="margin:0">Request #{{ r.id }}</h3>
      <span class="pill">Est. Fare: ${{ '%.2f'|format(r.fare) }}</span>
    </div>
    <p style="margin:.5rem 0 0 0"><strong>Pickup:</strong> {{ r.pickup }}</p>
    <p style="margin:.25rem 0 .5rem 0"><strong>Destination:</strong> {{ r.destination }}</p>
    <p class="muted" style="margin:0">Created: {{ r.created_at }}</p>

    <form method="POST" action="{{ url_for('driver_home.home') }}" style="margin-top:.75rem">
      <input type="hidden" name="trip_id" value="{{ r.id }}">
      <div class="actions">
        <button type="submit" name="decision" value="accept">Accept</button>
        <button type="submit" name="decision" value="decline" class="secondary">Decline</button>
      </div>
    </form>
  </article>
  {% else %}
  <p class="muted">No pending requests right now.</p>
  {% endfor %}
</section>
"""


TRIP_PROGRESS_BODY = """
<nav>
  <a href="{{ url_for('driver_home.home') }}" class="secondary">Driver Home</a>
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Rider Home</a>
</nav>

<h2>Trip In Progress (Driver)</h2>

{% if trip is none %}
  <p class="muted">Trip not found.</p>
{% else %}
  <section class="card">
    <header style="display:flex;align-items:center;justify-content:space-between;">
      <div>
        <strong>{{ trip.pickup }}</strong><br>
        <span style="font-size:.9rem;">to</span><br>
        <strong>{{ trip.destination }}</strong>
      </div>
      <span class="pill">{{ status_label }}</span>
    </header>

    <div class="stepper">
      <span class="step {% if trip.status in ['to_pickup','to_destination','completed'] %}active{% endif %}">
        To Pickup
      </span>
      <span class="step {% if trip.status in ['to_destination','completed'] %}active{% endif %}">
        To Destination
      </span>
      <span class="step {% if trip.status == 'completed' %}active{% endif %}">
        Complete
      </span>
    </div>

    <p class="muted" style="margin-top:.5rem;">Trip ID: {{ trip.id }} · Fare: ${{ '%.2f'|format(trip.fare) }}</p>
  </section>

  <section class="card" style="margin-top:1rem;">
    <h3 style="margin-top:0;">Map Navigation</h3>
    <div class="map">{{ fmap|safe }}</div>
    <p class="muted" style="margin-top:.5rem;">
      Static navigation preview for now. Later, plug in live turn-by-turn routing.
    </p>
  </section>

  <form method="POST" action="{{ url_for('driver_home.trip_progress', trip_id=trip.id) }}" style="margin-top:1rem;">
    <div class="actions">
      <button type="submit" name="action" value="start"
              {% if trip.status not in ['accepted','requested'] %}disabled{% endif %}>
        Start Trip
      </button>
      <button type="submit" name="action" value="arrived"
              {% if trip.status != 'to_pickup' %}disabled{% endif %}>
        Arrived at pickup
      </button>
      <button type="submit" name="action" value="end"
              {% if trip.status != 'to_destination' %}disabled{% endif %}>
        End Trip
      </button>
    </div>
    <p class="muted" style="margin-top:.5rem;">
      Current status: {{ status_label }}
    </p>
  </form>
{% endif %}
"""

@driver_home.route("/", methods=["GET", "POST"])
def home():
    banner = None
    if request.method == "POST":
        trip_id = request.form.get("trip_id", "").strip()
        decision = (request.form.get("decision") or "").strip()
        if trip_id.isdigit() and decision in {"accept", "decline"}:
            db.update_trip_status(int(trip_id), "accepted" if decision == "accept" else "declined")
            banner = {
                "title": f"Request #{trip_id} {'accepted' if decision=='accept' else 'declined'}.",
                "detail": "Status updated in SQLite (app.db).",
            }
    
    rows = db.get_pending_trips()
    requests = [
        {
            "id": row[0],
            "pickup": row[1],
            "destination": row[2],
            "strategy": row[3],
            "fare": row[4],
            "created_at": row[6],
        }
        for row in rows
    ]

    body = render_template_string(
        HOME_BODY,
        requests= requests,
        banner = banner
    )
    return render_template_string(BASE_HTML, body=body)


"""
  Trip In Progress (Driver)

  Displays current trip status ("To Pickup", "To Destination", "Complete")
  and a map, with actions:
    - Start Trip
    - Arrived at pickup
    - End Trip
"""
@driver_home.route("/trip/<int:trip_id>/progress", methods=["GET", "POST"])
def trip_progress(trip_id):
  row = db.get_trip_by_id(trip_id)
  if row is None:
    trip = None
    status_label = ""
  else:
    trip = {
        "id": row[0],
        "pickup": row[1],
        "destination": row[2],
        "strategy": row[3],
        "fare": row[4],
        "status": row[5],
    }
    
    # Handle state transitions via Buttons
    if request.method == "POST":
      action = (request.form.get("action") or "").strip()
      if action == "start" and trip["status"] in ["accepted", "requested"]:
        db.update_trip_status(trip_id, "to_pickup")
        trip["status"] = "to_pickup"
      elif action == "arrived" and trip["status"] == "to_pickup":
        db.update_trip_status(trip_id, "to_destination")
        trip["status"] = "to_destination"
      elif action == "end" and trip["status"] == "to_destination":
        db.update_trip_status(trip_id, "completed")
        trip["status"] = "completed"

    status_label = TRIP_STATUS_LABELS.get(trip["status"], trip["status"].title())
  
  fmap_html = make_driver_map()

  body = render_template_string(
      TRIP_PROGRESS_BODY,
      trip=trip,
      status_label=status_label,
      fmap=fmap_html,
  )
  return render_template_string(BASE_HTML, body=body)

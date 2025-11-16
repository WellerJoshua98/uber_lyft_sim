## Coded with help from chat gpt
from flask import Blueprint, Flask, render_template_string, request, url_for, redirect
import folium
import db

rider_home = Blueprint("rider_home", __name__)

def make_map():
    fmap = folium.Map(location=[40.758, -73.9855], zoom_start=12, tiles="OpenStreetMap")
    return fmap._repr_html_()

fare_strategy = {"Standard": 10.00, "Surge": 16.00, "Premium": 20.00}
def calculate_fare(strategy: str) -> float:
    return fare_strategy.get(strategy, 10.00)

def estimate_distance(pickup: str, destination: str) -> int:
    # Stub function: In real app, calculate based on addresses
    return 5

def estimate_eta(pickup: str, destination: str) -> int:
    # Stub function: In real app, calculate based on addresses
    return 10

BASE_HTML = """ 
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Rider Homepage</title>
  <link href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css" rel="stylesheet">
  <style>
    body { padding: 1rem; }
    .map { border-radius: 12px; overflow: hidden; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .actions { display:flex; gap:.5rem; flex-wrap:wrap; }
    .muted { color:#666; font-size:.9rem; }
     nav a { margin-right:.5rem; }
    .pill { padding:.2rem .6rem; border-radius:999px; background:#eef; font-size:.85rem; }
    .card { border:1px solid #e5e7eb; border-radius:12px; padding:1rem; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.04); }
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
        <a href="{{ url_for('rider_home.home') }}"><strong>Rider Home</strong></a>
        <a href="{{ url_for('driver_home.home') }}" class="secondary">Driver Home</a>
    </nav>

    <h2>Rider Homepage</h2>
    <p class="muted">Enter pickup and destination, choose fare strategy, and preview or request a trip.</p>

   <section class="card">
  <form method="POST" action="{{ url_for('rider_home.home') }}">
    <div class="grid-2">
      <label>
        Pickup Address
        <input type="text" name="pickup" placeholder="e.g., 350 5th Ave, New York, NY" value="{{ pickup or '' }}" required>
      </label>
      <label>
        Destination Address
        <input type="text" name="destination" placeholder="e.g., Times Square, New York, NY" value="{{ destination or '' }}" required>
      </label>
    </div>

    <label>
      Fare Strategy
      <select name="strategy">
        {% for s in ["Standard", "Surge", "Premium"] %}
          <option value="{{ s }}" {% if s == strategy %}selected{% endif %}>{{ s }}</option>
        {% endfor %}
      </select>
    </label>

    <div class="actions">
      <button type="submit" name="action" value="preview" class="contrast">Preview Route &amp; Fare</button>
      <button type="submit" name="action" value="request">Request Trip</button>
      <a role="button" href="{{ url_for('rider_home.trips') }}" class="secondary">View Past Trips</a>
    </div>
  </form>
</section>

{% if preview %}
<section style="margin-top:1rem" class="card">
  <header style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem">
    <strong>Map Preview</strong>
    <span class="pill">{{ strategy }}</span>
  </header>
  <div class="map">{{ fmap|safe }}</div>
  <p class="muted" style="margin-top:.5rem">Stub fare estimate: <strong>${{ '%.2f'|format(fare) }}</strong></p>
</section>
{% endif %}
"""

PREVIEW_BODY = """
<nav>
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Back to Rider Home</a>
  <a href="{{ url_for('driver_home.home') }}" class="secondary">Driver Home</a>
</nav>

<h2>Trip Preview</h2>
<p class="muted">Review your trip details before confirming your request.</p>

<section class="card">
  <header style="display:flex;align-items:center;justify-content:space-between;">
    <div>
      <strong>{{ pickup }}</strong><br>
      <span style="font-size:.9rem;">to</span><br>
      <strong>{{ destination }}</strong>
    </div>
    <span class="pill">{{ strategy }}</span>
  </header>

  <hr>

  <p style="margin:.25rem 0;"><strong>Estimated ETA:</strong> {{ eta_min }} minutes</p>
  <p style="margin:.25rem 0;"><strong>Estimated Distance:</strong> {{ "%.1f"|format(distance_km) }} km</p>
  <p style="margin:.25rem 0;"><strong>Estimated Fare:</strong> ${{ "%.2f"|format(fare) }}</p>
</section>

<section class="card" style="margin-top:1rem;">
  <h3 style="margin-top:0;">Route Preview</h3>
  <div class="map">{{ fmap|safe }}</div>
  <p class="muted" style="margin-top:.5rem;">
    Static preview map for now. Later, draw the actual route polyline between pickup and destination.
  </p>
</section>

<form method="POST" action="{{ url_for('rider_home.home') }}" style="margin-top:1rem;">
  <!-- carry data back as hidden inputs -->
  <input type="hidden" name="pickup" value="{{ pickup }}">
  <input type="hidden" name="destination" value="{{ destination }}">
  <input type="hidden" name="strategy" value="{{ strategy }}">
  <input type="hidden" name="distance_km" value="{{ distance_km }}">
  <input type="hidden" name="eta_min" value="{{ eta_min }}">
  <input type="hidden" name="fare" value="{{ fare }}">

  <div class="actions">
    <button type="submit" name="action" value="confirm">Confirm Request</button>
    <button type="submit" name="action" value="cancel" class="secondary">Cancel</button>
  </div>
</form>
"""

TRIPS_BODY = """
<nav>
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Back</a>
</nav>

<h2>Past Trips</h2>
<table>
  <thead>
    <tr>
      <th>ID</th><th>When</th><th>Pickup</th><th>Destination</th>
      <th>Strategy</th><th>Fare ($)</th><th>Status</th>
    </tr>
  </thead>
  <tbody>
    {% for t in trips %}
      <tr>
        <td>{{ t[0] }}</td>
        <td>{{ t[1] }}</td>
        <td>{{ t[2] }}</td>
        <td>{{ t[3] }}</td>
        <td>{{ t[4] }}</td>
        <td>{{ '%.2f'|format(t[5]) }}</td>
        <td>{{ t[6] }}</td>
      </tr>
    {% endfor %}
  </tbody>
</table>
"""

@rider_home.route("/", methods=["GET", "POST"])
def home():
    pickup = destination = ""
    strategy = "Standard"
    preview = False
    fare = None

    if request.method == "POST":
        pickup = request.form.get("pickup", "").strip()
        destination = request.form.get("destination", "").strip()
        strategy = request.form.get("strategy", "Standard")
        action = request.form.get("action")

        if action == "preview":
            preview_distance = estimate_distance(pickup, destination)
            preview_eta = estimate_eta(pickup, destination)
            fare = calculate_fare(strategy)
            fmap_html = make_map()

            body = render_template_string(
                PREVIEW_BODY,
                pickup=pickup,
                destination=destination,
                strategy=strategy,
                distance_km=preview_distance,
                eta_min=preview_eta,
                fare=fare,
                fmap=fmap_html
            )

            return render_template_string(BASE_HTML, body=body)
        elif action == "confirm":
             # Confirm from Trip Preview page: save trip, go to Past Trips
            fare = float(request.form.get("fare", calculate_fare(strategy)))
            db.create_trip(pickup, destination, strategy, fare)
            return redirect(url_for("rider_home.trips"))

        elif action == "request":
            # save trip to db
            fare = calculate_fare(strategy)
            db.create_trip(pickup, destination, strategy, fare)
            return redirect(url_for("rider_home.trips"))
    

    fmap_html = make_map()
    body = render_template_string(
        HOME_BODY,
        pickup=pickup,
        destination=destination,
        strategy=strategy,
        fmap=fmap_html,
        preview=preview,
        fare=fare
    )

    return render_template_string(BASE_HTML, body=body)


@rider_home.route("/trips")
def past_trips():
    trips = db.list_trips()
    body = render_template_string(TRIPS_BODY, trips=trips)
    return render_template_string(BASE_HTML, body=body)
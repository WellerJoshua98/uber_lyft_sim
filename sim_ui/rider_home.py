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

def get_driver_for_trip(tripId:int):
    return db.get_driver_for_trip(tripId)


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
      <a role="button" href="{{ url_for('rider_home.past_trips') }}" class="secondary">View Past Trips</a>
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
        <td>
          <a href="{{ url_for('rider_home.trip_summary', trip_id=t[0]) }}">View Summary</a>
        </td>
      </tr>
    {% endfor %}
  </tbody>
</table>
"""

TRIP_SUMMARY_BODY = """
<nav>
  <a href="{{ url_for('rider_home.trips') }}" class="secondary">Back to Past Trips</a>
  <a href="{{ url_for('driver_home.home') }}" class="secondary">Driver Home</a>
</nav>

<h2>Trip Summary</h2>
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
      <span class="pill">{{ trip.strategy }}</span>
    </header>

    <hr>

    <p style="margin:.25rem 0;"><strong>Trip ID:</strong> {{ trip.id }}</p>
    <p style="margin:.25rem 0;"><strong>Completed At:</strong> {{ trip.created_at }}</p>
    <p style="margin:.25rem 0;"><strong>Status:</strong> {{ trip.status }}</p>
    <p style="margin:.25rem 0;"><strong>Fare:</strong> ${{ "%.2f"|format(trip.fare) }}</p>
  </section>

  <section class="card" style="margin-top:1rem;">
    <h3 style="margin-top:0;">Leave a Review</h3>
    <form method="POST" action="{{ url_for('rider_home.trip_summary', trip_id=trip.id) }}">
      <label>
        Rating (1–5)
        <select name="rating" required>
          {% for r in [1,2,3,4,5] %}
            <option value="{{ r }}" {% if review and review.rating == r %}selected{% endif %}>{{ r }}</option>
          {% endfor %}
        </select>
      </label>

      <label>
        Comment (optional)
        <textarea name="comment" rows="3" placeholder="How was your trip?">{{ review.comment if review else "" }}</textarea>
      </label>

      <div class="actions">
        <button type="submit" name="action" value="submit-rating">Submit Rating</button>
        <a role="button" class="secondary" href="{{ url_for('rider_home.trip_receipt', trip_id=trip.id) }}">
          View Receipt
        </a>
      </div>
    </form>

    {% if review %}
      <p class="muted" style="margin-top:.5rem;">
        Last submitted rating: {{ review.rating }} ★ on {{ review.created_at }}
      </p>
    {% endif %}
  </section>
{% endif %}
"""

TRIP_RECEIPT_BODY = """
<nav>
  <a href="{{ url_for('rider_home.trip_summary', trip_id=trip.id) }}" class="secondary">Back to Trip Summary</a>
  <a href="{{ url_for('rider_home.trips') }}" class="secondary">Past Trips</a>
</nav>

<h2>Trip Receipt</h2>

{% if trip is none %}
  <p class="muted">Trip not found.</p>
{% else %}
  <section class="card">
    <p><strong>Trip ID:</strong> {{ trip.id }}</p>
    <p><strong>Date:</strong> {{ trip.created_at }}</p>
    <p><strong>Pickup:</strong> {{ trip.pickup }}</p>
    <p><strong>Destination:</strong> {{ trip.destination }}</p>
    <p><strong>Fare Strategy:</strong> {{ trip.strategy }}</p>

    <hr>

    <!-- Simple static breakdown; you can refine this later -->
    <p><strong>Base Fare:</strong> ${{ "%.2f"|format(trip.fare * 0.7) }}</p>
    <p><strong>Taxes & Fees:</strong> ${{ "%.2f"|format(trip.fare * 0.3) }}</p>
    <p><strong>Total Charged:</strong> ${{ "%.2f"|format(trip.fare) }}</p>
  </section>
{% endif %}
"""

NO_DRIVERS_BODY = """
<nav>
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Back to Rider Home</a>
  <a href="{{ url_for('driver_home.home') }}" class="secondary">Driver Home</a>
</nav>

<h2>No Drivers Available</h2>

<section class="card" style="margin-top:0.75rem;">
  <p style="font-size:1rem; margin-bottom:0.5rem;">
    We couldn&#39;t find any available drivers near your pickup location right now.
  </p>
 

  <form method="POST" action="{{ url_for('rider_home.no_drivers') }}" style="margin-top:1rem;">
    <!-- optional hidden fields if you want to carry the last pickup/destination -->
    <input type="hidden" name="pickup" value="{{ pickup or '' }}">
    <input type="hidden" name="destination" value="{{ destination or '' }}">

    <div class="actions">
      <button type="submit" name="action" value="try-again">Try Again</button>
      <button type="submit" name="action" value="change-pickup" class="secondary">Change Pickup</button>
    </div>
  </form>
</section>
"""

LIVE_TRIP_BODY = """
<nav>
  <a href="{{ url_for('rider_home.trips') }}" class="secondary">Past Trips</a>
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Rider Home</a>
</nav>

<h2>Live Trip</h2>

{% if trip is none %}
  <p class="muted">Trip not found.</p>
{% else %}
  {% if banner %}
    <article class="contrast">
      <strong>{{ banner.title }}</strong>
      <p class="muted">{{ banner.detail }}</p>
    </article>
  {% endif %}

  <section class="card">
    <header style="display:flex;align-items:center;justify-content:space-between;">
      <div>
        <strong>{{ trip.pickup }}</strong><br>
        <span style="font-size:.9rem;">to</span><br>
        <strong>{{ trip.destination }}</strong>
      </div>
      <span class="pill">{{ trip.status_label }}</span>
    </header>

    <hr>

    <h3 style="margin-top:0;">Driver &amp; Car</h3>
    <p style="margin:.25rem 0;"><strong>Driver:</strong> {{ driver.name }}</p>
    <p style="margin:.25rem 0;">
      <strong>Rating:</strong> {{ "%.1f"|format(driver.rating) }} ★
    </p>
    <p style="margin:.25rem 0;">
      <strong>Vehicle:</strong> {{ driver.vehicle_color }} {{ driver.vehicle_model }}
      ({{ driver.vehicle_plate }})
    </p>
    <p class="muted" style="margin-top:.25rem;">
      ETA: ~{{ driver.eta_min }} minutes · Trip ID: {{ trip.id }} · Fare: ${{ "%.2f"|format(trip.fare) }}
    </p>
  </section>

  <section class="card" style="margin-top:1rem;">
    <h3 style="margin-top:0;">Live Map</h3>
    <div class="map">{{ fmap|safe }}</div>
    <p class="muted" style="margin-top:.5rem;">
      Static map preview for now. Later, update this with live driver position and route.
    </p>
  </section>

  <form method="POST" action="{{ url_for('rider_home.live_trip', trip_id=trip.id) }}" style="margin-top:1rem;">
    <div class="actions">
      <button type="submit" name="action" value="contact">Contact Driver</button>
      <button type="submit" name="action" value="cancel" class="secondary"
              {% if trip.status in ['completed','cancelled'] %}disabled{% endif %}>
        Cancel Trip
      </button>
    </div>
    <p class="muted" style="margin-top:.5rem;">
      Current status: {{ trip.status_label }}
    </p>
  </form>
{% endif %}
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
            return redirect(url_for("rider_home.past_trips"))
        elif action == "cancel":
            # From Trip Preview: just go back to clean Rider Home
            return redirect(url_for("rider_home.home"))
        elif action == "request":
            # save trip to db
            fare = calculate_fare(strategy)
            db.create_trip(pickup, destination, strategy, fare)
            return redirect(url_for("rider_home.past_trips"))
    

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

@rider_home.route("/trip/<int:trip_id>", methods=["GET", "POST"])
def trip_summary(trip_id):
    row = db.get_trip_by_id(trip_id)
    if row is None:
        trip = None
        review = None
    else:
        trip = {
            "id": row[0],
            "created_at": row[1],
            "pickup": row[2],
            "destination": row[3],
            "strategy": row[4],
            "fare": row[5],
            "state": row[6]
        }
        rrow = db.get_review_by_trip_id(trip_id)
        review = None
        if rrow:
            review = {
                "id": rrow[0],
                "rating": rrow[2],
                "created_at": rrow[3]
            }
    
    if request.method == "POST" and trip is not None:
        action = request.form.get("action")
        if action == "submit-rating":
            rating_raw = request.form.get("rating", "").strip()

            try:
                rating = int(rating_raw)
            except ValueError:
                rating = None
            if rating and 1 <= rating <= 5:
                db.create_update_review(trip_id, rating)
                rrow = db.get_review_by_trip_id(trip_id)
                review = {
                    "id": rrow[0],
                    "rating": rrow[2],
                    "created_at": rrow[3]
                }
    
    body = render_template_string(TRIP_SUMMARY_BODY, trip=trip, review=review)
    return render_template_string(BASE_HTML, body=body)

@rider_home.route("/trip/<int:trip_id>/receipt")
def trip_receipt(trip_id):
    row = db.get_trip_by_id(trip_id)
    if row is None:
        trip = None
    else:
        trip = {
            "id": row[0],
            "created_at": row[1],
            "pickup": row[2],
            "destination": row[3],
            "strategy": row[4],
            "fare": row[5],
            "state": row[6]
        }
    
    body = render_template_string(TRIP_RECEIPT_BODY, trip=trip)
    return render_template_string(BASE_HTML, body=body)


"""
    Live Trip (Rider)

    Shows driver & car details, trip status, and map.
    Actions: "Contact Driver" and "Cancel Trip".
"""
@rider_home.route("/trip/<int:trip_id>/live", methods=["GET", "POST"])
def live_trip(trip_id):
    row = db.get_trip_by_id(trip_id)
    banner = None

    if row is None:
        trip = None
        driver = None
        fmap_html = make_map()
    else:
        trip = {
            "id": row[0],
            "created_at": row[1],
            "pickup": row[2],
            "destination": row[3],
            "strategy": row[4],
            "fare": row[5],
            "state": row[6]
        }

        # Map internal status -> nice label
        status_map = {
            "requested": "Requested",
            "accepted": "Accepted",
            "to_pickup": "To Pickup",
            "to_destination": "To Destination",
            "completed": "Complete",
            "declined": "Declined",
            "cancelled": "Cancelled",
        }

        trip["status_label"] = status_map.get(trip["state"], trip["state"].title())
        
        driver = get_driver_for_trip(trip_id)

        if request.method == "POST":
            action = request.form.get("action")

            if action == "contact":
                # UI-only: pretend we're opening a chat/call
                banner = {
                    "title": "Contacting driver…",
                    "detail": "This is a demo. In a real app, this would open in-app chat or call.",
                }
            elif action == "cancel" and trip["state"] not in ["completed", "cancelled"]:
                db.update_trip_status(trip_id, "cancelled")
                trip["state"] = "cancelled"
                trip["status_label"] = status_map["cancelled"]
                banner = {
                    "title": "Trip Cancelled",
                    "detail": "Your trip has been cancelled.",
                }
        fmap_html = make_map()

    body = render_template_string(
        LIVE_TRIP_BODY,
        trip=trip,
        driver=driver,
        fmap=fmap_html,
        banner=banner
    )
    return render_template_string(BASE_HTML, body=body)



@rider_home.route("/no_drivers", methods=["GET", "POST"])
def no_drivers():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "try-again":
            return redirect(url_for("rider_home.home"))
        elif action == "change-pickup":
            return redirect(url_for("rider_home.home"))
    
    body = render_template_string(
        NO_DRIVERS_BODY,
        pickup=request.form.get("pickup", ""),
        destination=request.form.get("destination", "")
    )
    return render_template_string(BASE_HTML, body=body)
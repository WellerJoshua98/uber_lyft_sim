from flask import Blueprint, Flask, render_template_string, request
import folium

rider_home = Blueprint("rider_home", __name__)

def make_map():
    fmap = folium.Map(location=[40.758, -73.9855], zoom_start=12, tiles="OpenStreetMap")
    return fmap._repr_html_()

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
    <h2>Rider Homepage</h2>
    <p class="muted">Enter pickup and destination, choose fare strategy, and preview or request a trip.</p>

    <form method="POST" action="/">
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

    <section style="margin-top:1rem">
    <h3>Map Preview</h3>
    <div class="map">{{ fmap|safe }}</div>
    </section>
"""

TRIPS_BODY = """
<h2>Past Trips (Stub)</h2>
<p class="muted">Placeholder — logic can be added later.</p>
<table>
  <thead><tr><th>Date</th><th>Pickup</th><th>Destination</th><th>Strategy</th></tr></thead>
  <tbody><tr><td>—</td><td>—</td><td>—</td><td>—</td></tr></tbody>
</table>
<p><a role="button" href="{{ url_for('rider_home.home') }}">Back</a></p>
"""

@rider_home.route("/", methods=["GET", "POST"])
def home():
    pickup = destination = ""
    strategy = "Standard"

    if request.method == "POST":
        pickup = request.form.get("pickup", "")
        destination = request.form.get("destination", "")
        strategy = request.form.get("strategy", "Standard")
    
    fmap_html = make_map()
    body = render_template_string(
        HOME_BODY,
        pickup=pickup,
        destination=destination,
        strategy=strategy,
        fmap=fmap_html,
    )

    return render_template_string(BASE_HTML, body=body)


@rider_home.route("/trips")
def past_trips():
    body = render_template_string(TRIPS_BODY)
    return render_template_string(BASE_HTML, body=body)

if __name__ == "__main__":
    rider_home.run(debug=True)
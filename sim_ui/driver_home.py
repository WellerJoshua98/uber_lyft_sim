## Coded with help from chat gpt
from flask import Blueprint, render_template_string, request
import folium
import db
from trip_management import Trip
from user_classes import Rider, Driver, TripState
from fare_calc import FareStrategyFactory

driver_home = Blueprint("driver_home", __name__)

def create_rider_from_trip_data(trip_row) -> Rider:
    """Create a Rider object from trip database data with proper user lookup"""
    # Extract user_id from trip row (at index 8 based on schema: id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id)
    user_id = trip_row[8] if len(trip_row) > 8 else None
    
    if user_id:
        try:
            # Look up the actual user in the database
            user_record = db.get_user_by_id(user_id)
            if user_record:
                # users table layout: id, name, rating, role, created_at
                db_id, db_name, db_rating, db_role, db_created_at = user_record
                # Generate email from name (since DB doesn't have email field)
                email = f"{db_name.lower().replace(' ', '').replace('-', '')}@example.com" if db_name else "user@example.com"
                phone = ""  # DB doesn't have phone field
                
                return Rider(user_id=str(db_id), name=db_name, email=email, phone=phone)
        except Exception as e:
            print(f"Error looking up user {user_id}: {e}")
    
    # Fallback to guest rider if user_id is missing or lookup fails
    return Rider(user_id="guest", name="Anonymous Rider", email="guest@example.com", phone="")

def create_rider_from_user_id(user_id: int) -> Rider:
    """Create a Rider object from a user_id with database lookup"""
    try:
        user_record = db.get_user_by_id(user_id)
        if user_record:
            # users table layout: id, name, rating, role, created_at
            db_id, db_name, db_rating, db_role, db_created_at = user_record
            # Generate email from name (since DB doesn't have email field)
            email = f"{db_name.lower().replace(' ', '').replace('-', '')}@example.com" if db_name else "user@example.com"
            phone = ""  # DB doesn't have phone field
            
            return Rider(user_id=str(db_id), name=db_name, email=email, phone=phone)
    except Exception as e:
        print(f"Error looking up user {user_id}: {e}")
    
    # Fallback to guest rider if lookup fails
    return Rider(user_id=str(user_id) if user_id else "guest", name="Anonymous Rider", email="guest@example.com", phone="")

# --------- Map helper for driver view ---------
def make_driver_map():
    # Static center for now; swap with real nav later
    fmap = folium.Map(location=[40.758, -73.9855], zoom_start=12, tiles="OpenStreetMap")
    return fmap._repr_html_()

# --- Get real trip requests from database ---
def get_pending_trip_requests():
    """Get pending trip requests from database and convert to Trip objects"""
    pending_trips = db.get_pending_trips()
    trip_objects = []
    
    for row in pending_trips:
        # Create a Trip object from database row
        trip_data = {
            "id": row[0],
            "created_at": row[1],
            "pickup": row[2],
            "destination": row[3],
            "strategy": row[4],
            "fare": row[5],
            "state": row[6],
            "distance": row[7] if len(row) > 7 else 5,  # Default distance if not set
        }
        
        # Create rider object from trip data (look up actual user)
        rider = create_rider_from_trip_data(row)
        
        # Recreate Trip object for OOP functionality
        trip_obj = Trip(trip_data["pickup"], trip_data["destination"], rider, trip_data["strategy"])
        trip_obj.trip_id = trip_data["id"]  # Use database ID
        trip_obj.set_route_info(float(trip_data["distance"]), 10.0)  # Mock duration
        
        # Convert to dictionary for template compatibility
        trip_request = {
            "id": trip_data["id"],
            "pickup": trip_data["pickup"],
            "destination": trip_data["destination"],
            "fare": trip_obj.base_fare,  # Use calculated fare from strategy
            "eta": "Now",  # Mock ETA
            "strategy": trip_data["strategy"],
            "trip_object": trip_obj  # Keep reference to Trip object
        }
        trip_objects.append(trip_request)
    
    return trip_objects

def get_mock_requests():
    """Keep original mock function for fallback"""
    return [
        {"id": "rq-101", "pickup": "350 5th Ave, New York, NY", "destination": "Times Square, New York, NY", "fare": 14.80, "eta": "Now"},
        {"id": "rq-102", "pickup": "1 Liberty Island, NY", "destination": "Brooklyn Bridge, NY", "fare": 22.10, "eta": "1 min"},
        {"id": "rq-103", "pickup": "JFK Terminal 4", "destination": "Midtown Manhattan", "fare": 45.30, "eta": "3 mins"}
    ]

def accept_trip_with_objects(trip_id: int, driver_name: str = "Default Driver") -> bool:
    """Accept a trip using Trip object functionality"""
    try:
        # Get trip from database
        row = db.get_trip_by_id(trip_id)
        if not row:
            return False
        
        # Create Trip object with proper rider lookup
        rider = create_rider_from_trip_data(row)
        trip_obj = Trip(row[2], row[3], rider, row[4])  # pickup, destination, rider, strategy
        trip_obj.trip_id = trip_id
        
        # Create driver object
        driver = Driver(user_id="2", name=driver_name, email="driver@example.com", phone="555-0456",
                       vehicle_type="Toyota Prius", license_plate="ABC123")
        
        # Accept the trip using OOP method
        trip_obj.accept(driver)
        
        # Update database
        db.update_trip_from_object(trip_id, trip_obj)
        
        return True
    except Exception as e:
        print(f"Error accepting trip: {e}")
        return False


# Status label mapping for UI - updated to match TripState enum
TRIP_STATUS_LABELS = {
    "requested": "Requested",
    "accepted": "Accepted", 
    "in_progress": "In Progress",
    "completed": "Completed",
    "declined": "Declined",
    "cancelled": "Cancelled",
    # Legacy mappings for backward compatibility
    "to_pickup": "To Pickup",
    "to_destination": "To Destination",
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
  <a href="{{ url_for('driver_home.advanced_driver') }}" class="contrast">Advanced Driver Demo</a>
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Rider Home</a>
</nav>

<h2>Driver Homepage</h2>
<p class="muted">Incoming ride requests. Accept or decline. Use Advanced Demo for Trip object integration.</p>

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
            trip_id_int = int(trip_id)
            
            if decision == "accept":
                # Use OOP method for accepting trips
                success = accept_trip_with_objects(trip_id_int, "Professional Driver")
                if success:
                    banner = {
                        "title": f"Request #{trip_id} accepted using Trip object!",
                        "detail": "Trip state updated using Observer pattern.",
                    }
                else:
                    banner = {
                        "title": f"Failed to accept request #{trip_id}",
                        "detail": "There was an error processing the request.",
                    }
            else:  # decline
                # For decline, we can still use simple database update or create Trip object
                db.update_trip_status(trip_id_int, "declined")
                banner = {
                    "title": f"Request #{trip_id} declined.",
                    "detail": "Status updated in database.",
                }
    
    # Get pending trip requests using Trip object integration
    requests = get_pending_trip_requests()
    
    # Fallback to old system if no real requests
    if not requests:
        requests = get_mock_requests()

    body = render_template_string(
        HOME_BODY,
        requests=requests,
        banner=banner
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
        # Create Trip object for OOP state management with proper rider lookup
        rider = create_rider_from_trip_data(row)
        trip_obj = Trip(row[2], row[3], rider, row[4])  # pickup, destination, strategy
        trip_obj.trip_id = trip_id
        
        # Set current state based on database
        current_state = row[6] if len(row) > 6 else "requested"
        
        trip = {
            "id": row[0],
            "pickup": row[2],
            "destination": row[3], 
            "strategy": row[4],
            "fare": row[5],
            "status": current_state,
        }
        
        # Handle state transitions using Trip object methods
        if request.method == "POST":
            action = (request.form.get("action") or "").strip()
            
            if action == "start" and current_state in ["accepted", "requested"]:
                # Start the trip (transition to in_progress)
                trip_obj.start()
                db.update_trip_from_object(trip_id, trip_obj)
                trip["status"] = trip_obj.state.value
                
            elif action == "complete" and current_state in ["accepted", "in_progress"]:
                # Complete the trip
                trip_obj.complete()
                db.update_trip_from_object(trip_id, trip_obj)
                trip["status"] = trip_obj.state.value

        status_label = TRIP_STATUS_LABELS.get(trip["status"], trip["status"].title())
    
    fmap_html = make_driver_map()

    body = render_template_string(
        TRIP_PROGRESS_BODY,
        trip=trip,
        status_label=status_label,
        fmap=fmap_html,
    )
    return render_template_string(BASE_HTML, body=body)

@driver_home.route("/advanced-driver", methods=["GET", "POST"])
def advanced_driver():
    """Demonstrate advanced Trip object functionality from driver perspective"""
    if request.method == "POST":
        action = request.form.get("action")
        trip_id = request.form.get("trip_id")
        
        if action == "simulate_trip_lifecycle" and trip_id and trip_id.isdigit():
            trip_id_int = int(trip_id)
            
            # Get trip from database and create Trip object with proper rider lookup
            row = db.get_trip_by_id(trip_id_int)
            if row:
                rider = create_rider_from_trip_data(row)
                trip_obj = Trip(row[2], row[3], rider, row[4])
                trip_obj.trip_id = trip_id_int
                
                # Create driver
                driver = Driver(user_id="2", name="Advanced Driver", email="driver@example.com", phone="555-0456",
                              vehicle_type="Tesla Model 3", license_plate="TESLA123")
                
                # Simulate complete trip lifecycle with Observer pattern
                class DriverNotificationObserver:
                    def __init__(self):
                        self.notifications = []
                    
                    def update(self, trip, old_state, new_state):
                        self.notifications.append(f"Driver notified: Trip {trip.trip_id} changed from {old_state.value} to {new_state.value}")
                
                observer = DriverNotificationObserver()
                trip_obj.attach(observer)
                
                # Progress through states
                trip_obj.accept(driver)
                db.update_trip_from_object(trip_id_int, trip_obj)
                
                trip_obj.start()
                db.update_trip_from_object(trip_id_int, trip_obj)
                
                trip_obj.complete()
                db.update_trip_from_object(trip_id_int, trip_obj)
                
                return render_template_string(BASE_HTML, body=f"""
                <nav>
                    <a href="{{ url_for('driver_home.advanced_driver') }}" class="secondary">Back to Advanced Driver</a>
                    <a href="{{ url_for('driver_home.home') }}" class="secondary">Driver Home</a>
                </nav>
                
                <h2>Trip Lifecycle Simulation Complete</h2>
                
                <section class="card">
                    <h3>Trip Object Information</h3>
                    <p><strong>Trip ID:</strong> {trip_obj.trip_id}</p>
                    <p><strong>Final State:</strong> {trip_obj.state.value}</p>
                    <p><strong>Driver:</strong> {driver.name}</p>
                    <p><strong>Vehicle:</strong> {driver.vehicle_type}</p>
                    <p><strong>Strategy Used:</strong> {trip_obj.fare_strategy.get_strategy_name()}</p>
                    <p><strong>Final Fare:</strong> ${trip_obj.base_fare:.2f}</p>
                </section>
                
                <section class="card" style="margin-top:1rem;">
                    <h3>Observer Notifications</h3>
                    {'<br>'.join(observer.notifications)}
                </section>
                """)
    
    # Get available trips for demonstration
    pending_requests = get_pending_trip_requests()
    
    advanced_driver_body = """
    <nav>
        <a href="{{ url_for('driver_home.home') }}" class="secondary">Back to Driver Home</a>
        <a href="{{ url_for('rider_home.home') }}" class="secondary">Rider Home</a>
    </nav>
    
    <h2>Advanced Driver Management</h2>
    <p class="muted">Demonstration of Trip object integration from driver perspective</p>
    
    <section class="card">
        <h3>Available Trip Requests</h3>
        {% if requests %}
            {% for req in requests %}
            <article class="card" style="margin-bottom:1rem;">
                <header style="display:flex;align-items:center;justify-content:space-between;">
                    <div>
                        <strong>{{ req.pickup }}</strong><br>
                        <span style="font-size:.9rem;">to</span><br>
                        <strong>{{ req.destination }}</strong>
                    </div>
                    <span class="pill">${{ "%.2f"|format(req.fare) }}</span>
                </header>
                
                <p style="margin:.5rem 0;">
                    <strong>Strategy:</strong> {{ req.strategy }}<br>
                    <strong>Trip ID:</strong> {{ req.id }}
                </p>
                
                <form method="POST" style="margin-top:.5rem;">
                    <input type="hidden" name="trip_id" value="{{ req.id }}">
                    <button type="submit" name="action" value="simulate_trip_lifecycle">
                        Simulate Complete Trip Lifecycle
                    </button>
                </form>
            </article>
            {% endfor %}
        {% else %}
            <p class="muted">No pending trips. Create some trips from the Rider Home to test this feature.</p>
        {% endif %}
    </section>
    
    <section class="card" style="margin-top:1rem;">
        <h3>Integration Features Demonstrated</h3>
        <ul>
            <li><strong>Observer Pattern:</strong> Real-time notifications when trip state changes</li>
            <li><strong>State Management:</strong> Proper OOP state transitions (requested → accepted → in_progress → completed)</li>
            <li><strong>Driver Assignment:</strong> Trip objects properly track assigned drivers</li>
            <li><strong>Strategy Pattern:</strong> Different fare calculation strategies</li>
            <li><strong>Database Sync:</strong> Trip objects sync with database automatically</li>
        </ul>
    </section>
    """
    
    body = render_template_string(advanced_driver_body, requests=pending_requests)
    return render_template_string(BASE_HTML, body=body)

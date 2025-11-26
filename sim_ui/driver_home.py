from flask import Blueprint, render_template_string, request, flash, redirect, url_for
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
                # users table layout: id, name, rating, role, created_at, vehicle_type, license_plate
                db_id, db_name, db_rating, db_role, db_created_at, vehicle_type, license_plate = user_record
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
            # users table layout: id, name, rating, role, created_at, vehicle_type, license_plate
            db_id, db_name, db_rating, db_role, db_created_at, vehicle_type, license_plate = user_record
            # Generate email from name (since DB doesn't have email field)
            email = f"{db_name.lower().replace(' ', '').replace('-', '')}@example.com" if db_name else "user@example.com"
            phone = ""  # DB doesn't have phone field
            
            return Rider(user_id=str(db_id), name=db_name, email=email, phone=phone)
    except Exception as e:
        print(f"Error looking up user {user_id}: {e}")
    
    # Fallback to guest rider if lookup fails
    return Rider(user_id=str(user_id) if user_id else "guest", name="Anonymous Rider", email="guest@example.com", phone="")

def create_driver_from_user_id(user_id: int) -> Driver:
    """Create a Driver object from a user_id with database lookup"""
    try:
        user_record = db.get_user_by_id(user_id)
        if user_record:
            # users table layout: id, name, rating, role, created_at, vehicle_type, license_plate
            db_id, db_name, db_rating, db_role, db_created_at, vehicle_type, license_plate = user_record
            # Generate email from name (since DB doesn't have email field)
            email = f"{db_name.lower().replace(' ', '').replace('-', '')}@example.com" if db_name else "driver@example.com"
            phone = ""  # DB doesn't have phone field
            
            # Use database vehicle info or defaults if not set
            vehicle_type = vehicle_type or "Toyota Prius"  # Default if None
            license_plate = license_plate or f"DRV{db_id:03d}"  # Generate if None
            
            return Driver(user_id=str(db_id), name=db_name, email=email, phone=phone,
                         vehicle_type=vehicle_type, license_plate=license_plate)
    except Exception as e:
        print(f"Error looking up driver {user_id}: {e}")
    
    # Fallback to guest driver if lookup fails
    return Driver(user_id=str(user_id) if user_id else "guest", name="Anonymous Driver", 
                 email="guest@example.com", phone="", vehicle_type="Unknown Vehicle", 
                 license_plate="UNKNOWN")

def get_available_drivers_with_status():
    """Get all drivers and their availability status"""
    drivers = db.get_all_drivers()
    driver_list = []
    
    for driver_row in drivers:
        # users table layout: id, name, rating, role, created_at, vehicle_type, license_plate
        driver_id, name, rating, role, created_at, vehicle_type, license_plate = driver_row
        
        # Check if driver has any active trips
        active_trip = db.get_active_trip_for_driver(driver_id)
        is_available = active_trip is None
        
        driver_info = {
            'id': driver_id,
            'name': name,
            'rating': rating,
            'created_at': created_at,
            'vehicle_type': vehicle_type,
            'license_plate': license_plate,
            'is_available': is_available,
            'status': 'Available' if is_available else f'Busy (Trip #{active_trip[0]})' if active_trip else 'Available'
        }
        driver_list.append(driver_info)
    
    return driver_list

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
  <a href="{{ url_for('rider_home.home') }}" class="secondary">Rider Home</a>
</nav>

<h2>Driver Homepage</h2>

{% with messages = get_flashed_messages() %}
  {% if messages %}
    <section class="flash-messages">
      {% for message in messages %}
        <article class="contrast" style="margin-bottom: 1rem;">
          <p>{{ message }}</p>
        </article>
      {% endfor %}
    </section>
  {% endif %}
{% endwith %}

<!-- Driver Selection Section -->
<section class="card" style="margin-bottom: 2rem;">
  <h3 style="margin-top: 0;">Select Driver</h3>
  
  {% if drivers %}
    <form method="POST" action="{{ url_for('driver_home.home') }}" style="margin-bottom: 1rem;">
      <fieldset>
        <label for="driver_selection">Choose an available driver:</label>
        <select name="selected_driver_id" id="driver_selection" required>
          <option value="">-- Select a Driver --</option>
          {% for driver in drivers %}
            <option value="{{ driver.id }}" 
                    {% if not driver.is_available %}disabled{% endif %}
                    {% if selected_driver and selected_driver.id == driver.id %}selected{% endif %}>
              {{ driver.name }} ({{ driver.vehicle_type or 'No Vehicle' }} - {{ driver.license_plate or 'No Plate' }}, Rating: {{ driver.rating }}) - {{ driver.status }}
            </option>
          {% endfor %}
        </select>
        <button type="submit" name="action" value="select_driver">Select Driver</button>
      </fieldset>
    </form>
  {% else %}
    <p class="muted">No drivers found in the database.</p>
  {% endif %}

  <details>
    <summary>Create New Driver</summary>
    <form method="POST" action="{{ url_for('driver_home.create_driver') }}" style="margin-top: 1rem;">
      <fieldset>
        <label for="driver_name">Driver Name:</label>
        <input type="text" id="driver_name" name="driver_name" required placeholder="Enter driver name">
        
        <label for="driver_rating">Rating:</label>
        <select id="driver_rating" name="driver_rating" required>
          <option value="">-- Select Rating --</option>
          <option value="5.0">5.0 - Excellent</option>
          <option value="4.8">4.8 - Very Good</option>
          <option value="4.5">4.5 - Good</option>
          <option value="4.0">4.0 - Fair</option>
          <option value="3.5">3.5 - Average</option>
        </select>
        
        <label for="vehicle_type">Vehicle Type:</label>
        <select id="vehicle_type" name="vehicle_type" required>
          <option value="">-- Select Vehicle Type --</option>
          <option value="Toyota Prius">Toyota Prius</option>
          <option value="Honda Civic">Honda Civic</option>
          <option value="Tesla Model 3">Tesla Model 3</option>
          <option value="Nissan Altima">Nissan Altima</option>
          <option value="Ford Fusion">Ford Fusion</option>
          <option value="Chevrolet Malibu">Chevrolet Malibu</option>
          <option value="Hyundai Elantra">Hyundai Elantra</option>
          <option value="Volkswagen Jetta">Volkswagen Jetta</option>
        </select>
        
        <label for="license_plate">License Plate:</label>
        <input type="text" id="license_plate" name="license_plate" required placeholder="Enter license plate (e.g., ABC123)" maxlength="10">
        
        <button type="submit">Create Driver</button>
      </fieldset>
    </form>
  </details>
</section>

{% if selected_driver %}
<section class="card" style="margin-bottom: 2rem; background-color: #f0f7ff;">
  <h4 style="margin-top: 0; color: #0066cc;">
    Active Driver: {{ selected_driver.name }} (Rating: {{ selected_driver.rating }})
  </h4>
  <p class="muted">Vehicle: {{ selected_driver.vehicle_type or 'Not specified' }} | Plate: {{ selected_driver.license_plate or 'Not specified' }}</p>
  <p class="muted">Status: {{ selected_driver.status }}</p>
  
  {% if not selected_driver.is_available %}
    <p><em>This driver is currently busy and cannot review new requests.</em></p>
  {% endif %}
</section>
{% endif %}

<!-- Trip Requests Section -->
{% if selected_driver %}
  {% if selected_driver.is_available %}
    <h3>Incoming Ride Requests</h3>
    <p class="muted">{{ selected_driver.name }} can review and respond to these requests.</p>
    
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
          <input type="hidden" name="selected_driver_id" value="{{ selected_driver.id }}">
          <div class="actions">
            <button type="submit" name="decision" value="accept">Accept for {{ selected_driver.name }}</button>
            <button type="submit" name="decision" value="decline" class="secondary">Decline</button>
          </div>
        </form>
      </article>
      {% else %}
      <p class="muted">No pending requests right now.</p>
      {% endfor %}
    </section>
  {% else %}
    <section class="card">
      <h3>Driver Busy</h3>
      <p>{{ selected_driver.name }} is currently busy with another trip and cannot review new requests.</p>
      <p class="muted">Please select an available driver or wait for them to complete their current trip.</p>
    </section>
  {% endif %}
{% else %}
  <section class="card">
    <h3>No Driver Selected</h3>
    <p>Please select an available driver above to review trip requests.</p>
  </section>
{% endif %}
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
    selected_driver = None
    
    # Get driver selection from session or form
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        
        # Handle driver selection
        if action == "select_driver":
            selected_driver_id = request.form.get("selected_driver_id", "").strip()
            if selected_driver_id and selected_driver_id.isdigit():
                driver_record = db.get_user_by_id(int(selected_driver_id))
                if driver_record:
                    selected_driver = {
                        'id': driver_record[0],
                        'name': driver_record[1],
                        'rating': driver_record[2],
                        'role': driver_record[3],
                        'created_at': driver_record[4],
                        'vehicle_type': driver_record[5] if len(driver_record) > 5 else None,
                        'license_plate': driver_record[6] if len(driver_record) > 6 else None,
                        'is_available': db.get_active_trip_for_driver(driver_record[0]) is None,
                        'status': 'Available' if db.get_active_trip_for_driver(driver_record[0]) is None else 'Busy'
                    }
                    flash(f"Selected driver: {selected_driver['name']}")
                else:
                    flash("Driver not found!")
            else:
                flash("Please select a valid driver!")
        
        # Handle trip decisions (accept/decline)
        else:
            trip_id = request.form.get("trip_id", "").strip()
            decision = request.form.get("decision", "").strip()
            selected_driver_id = request.form.get("selected_driver_id", "").strip()
            
            if trip_id.isdigit() and decision in {"accept", "decline"} and selected_driver_id and selected_driver_id.isdigit():
                trip_id_int = int(trip_id)
                driver_id_int = int(selected_driver_id)
                
                # Check if driver is still available
                if db.get_active_trip_for_driver(driver_id_int):
                    flash("Driver is no longer available!")
                elif decision == "accept":
                    # Assign driver to trip
                    success = db.assign_driver_to_trip(trip_id_int, driver_id_int)
                    if success:
                        driver_record = db.get_user_by_id(driver_id_int)
                        driver_name = driver_record[1] if driver_record else "Driver"
                        banner = {
                            "title": f"Request #{trip_id} accepted by {driver_name}!",
                            "detail": "Trip has been assigned and accepted.",
                        }
                        flash(f"Trip #{trip_id} successfully assigned to {driver_name}")
                    else:
                        banner = {
                            "title": f"Failed to accept request #{trip_id}",
                            "detail": "The trip may have been taken by another driver.",
                        }
                        flash("Failed to assign trip - it may have been taken already!")
                else:  # decline
                    db.update_trip_status(trip_id_int, "declined")
                    banner = {
                        "title": f"Request #{trip_id} declined.",
                        "detail": "Trip request has been declined.",
                    }
                    flash(f"Trip #{trip_id} declined")
            elif trip_id.isdigit() and decision in {"accept", "decline"}:
                flash("Please select a driver first!")
    
    # Get all drivers and their availability
    drivers = get_available_drivers_with_status()
    
    # Get pending trip requests 
    requests = get_pending_trip_requests()
    
    # Fallback to old system if no real requests
    if not requests:
        requests = get_mock_requests()

    body = render_template_string(
        HOME_BODY,
        requests=requests,
        banner=banner,
        drivers=drivers,
        selected_driver=selected_driver
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

@driver_home.route("/create-driver", methods=["POST"])
def create_driver():
    """Create a new driver"""
    driver_name = request.form.get("driver_name", "").strip()
    driver_rating = request.form.get("driver_rating", "").strip()
    vehicle_type = request.form.get("vehicle_type", "").strip()
    license_plate = request.form.get("license_plate", "").strip().upper()
    
    if not driver_name:
        flash("Driver name is required!")
        return redirect(url_for('driver_home.home'))
    
    if not driver_rating:
        flash("Driver rating is required!")
        return redirect(url_for('driver_home.home'))
    
    if not vehicle_type:
        flash("Vehicle type is required!")
        return redirect(url_for('driver_home.home'))
    
    if not license_plate:
        flash("License plate is required!")
        return redirect(url_for('driver_home.home'))
    
    # Validate license plate format (basic check)
    if len(license_plate) < 3 or len(license_plate) > 10:
        flash("License plate must be between 3 and 10 characters!")
        return redirect(url_for('driver_home.home'))
    
    try:
        # Check if license plate already exists
        existing_drivers = db.get_all_drivers()
        plate_exists = any(driver[6] and driver[6].upper() == license_plate for driver in existing_drivers if driver[6])
        
        if plate_exists:
            flash("License plate already exists!")
            return redirect(url_for('driver_home.home'))
        
        # Create the driver in database with vehicle info
        driver_id = db.create_user(driver_name, driver_rating, "driver", vehicle_type, license_plate)
        flash(f"Driver '{driver_name}' created successfully with vehicle {vehicle_type} (plate: {license_plate})!")
    except Exception as e:
        flash(f"Error creating driver: {str(e)}")
    
    return redirect(url_for('driver_home.home'))

@driver_home.route("/create-demo-drivers", methods=["POST"])
def create_demo_drivers():
    """Create demo drivers for testing"""
    demo_drivers = [
        ("Alex Rodriguez", "4.9", "Toyota Prius", "ALX001"),
        ("Sarah Chen", "4.8", "Honda Civic", "SCH002"),
        ("Mike Johnson", "4.7", "Tesla Model 3", "MJK003"),
        ("Emily Davis", "4.9", "Nissan Altima", "EMD004"),
        ("Robert Kim", "4.6", "Ford Fusion", "RBK005"),
        ("Lisa Thompson", "4.8", "Chevrolet Malibu", "LST006"),
        ("David Wilson", "4.7", "Hyundai Elantra", "DVW007"),
        ("Jennifer Brown", "4.9", "Volkswagen Jetta", "JBR008"),
        ("Carlos Martinez", "4.5", "Toyota Camry", "CAM009"),
        ("Angela White", "4.8", "Honda Accord", "AGW010"),
        ("James Taylor", "4.6", "Tesla Model Y", "JMT011"),
        ("Maria Garcia", "4.9", "Nissan Sentra", "MGA012"),
        ("Thomas Anderson", "4.7", "Ford Escape", "THA013"),
        ("Rachel Green", "4.8", "Chevrolet Cruze", "RGR014"),
        ("Kevin O'Brien", "4.5", "Hyundai Sonata", "KOB015")
    ]
    
    created_count = 0
    errors = []
    
    for name, rating, vehicle_type, license_plate in demo_drivers:
        try:
            # Check if driver already exists by name (simple check)
            existing_drivers = db.get_all_drivers()
            name_exists = any(driver[1].lower() == name.lower() for driver in existing_drivers)
            plate_exists = any(driver[6] and driver[6].upper() == license_plate.upper() for driver in existing_drivers if driver[6])
            
            if not name_exists and not plate_exists:
                driver_id = db.create_user(name, rating, "driver", vehicle_type, license_plate)
                created_count += 1
            elif plate_exists:
                errors.append(f"License plate {license_plate} already exists")
        except Exception as e:
            errors.append(f"Error creating {name}: {str(e)}")
    
    if created_count > 0:
        flash(f"Successfully created {created_count} demo drivers with vehicle information!")
    
    if errors:
        flash(f"Errors occurred: {'; '.join(errors)}")
    
    if created_count == 0 and not errors:
        flash("All demo drivers already exist!")
    
    return redirect(url_for('driver_home.home'))

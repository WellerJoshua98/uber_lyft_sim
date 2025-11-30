## Coded with help from chat gpt
from typing import Optional
from flask import Blueprint, Flask, render_template_string, request, url_for, redirect, session, flash
import folium
import db
from trip_management import Trip
from user_classes import Rider, Driver, TripState
from fare_calc import FareStrategyFactory
from map_integration import MapService, MockMapService
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create an instance of the map service
try:
    if os.getenv("ORS_API_KEY"):
        map_service = MapService()
        print("Using real MapService with OpenRouteService API")
    else:
        map_service = MockMapService()
        print("Using MockMapService (no API key found)")
except Exception as e:
    print(f"Failed to initialize map service: {e}")
    map_service = MockMapService()  # Fallback instance

rider_home = Blueprint("rider_home", __name__)

# Status label mapping for UI - consistent with driver_home
TRIP_STATUS_LABELS = {
    "requested": "Requested",
    "accepted": "Accepted", 
    "in_progress": "In Progress",
    "completed": "Completed",
    "declined": "Declined",
    "cancelled": "Cancelled",
    # Handle enum case variations
    "In_Progress": "In Progress",
    "IN_PROGRESS": "In Progress",
}

def get_status_label(status):
    """Get user-friendly status label"""
    return TRIP_STATUS_LABELS.get(status, status.title() if status else "Unknown")

# Map service already initialized above

def make_map(pickup_coords=None, dest_coords=None):
    """Enhanced map generation with route visualization"""
    # Default center (NYC)
    center_lat, center_lon = 40.758, -73.9855
    
    if pickup_coords and dest_coords:
        # Center the map between pickup and destination
        center_lat = (pickup_coords[0] + dest_coords[0]) / 2
        center_lon = (pickup_coords[1] + dest_coords[1]) / 2
    elif pickup_coords:
        center_lat, center_lon = pickup_coords
    elif dest_coords:
        center_lat, center_lon = dest_coords
    
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="OpenStreetMap")
    
    # Add markers if coordinates are provided
    if pickup_coords:
        folium.Marker(
            pickup_coords,
            popup="Pickup Location",
            tooltip="Pickup",
            icon=folium.Icon(color="green", icon="play")
        ).add_to(fmap)
    
    if dest_coords:
        folium.Marker(
            dest_coords,
            popup="Destination",
            tooltip="Destination", 
            icon=folium.Icon(color="red", icon="stop")
        ).add_to(fmap)
    
    # Draw route line if both points exist
    if pickup_coords and dest_coords:
        folium.PolyLine(
            [pickup_coords, dest_coords],
            weight=5,
            color="blue",
            opacity=0.8,
            popup="Route"
        ).add_to(fmap)
    
    return fmap._repr_html_()

def get_strategy_descriptions() -> dict:
    """Get descriptions for all available fare strategies"""
    strategies = {}
    try:
        for strategy_name in FareStrategyFactory.get_available_strategies():
            strategy_obj = FareStrategyFactory.create_strategy(strategy_name)
            strategies[strategy_name] = {
                "description": strategy_obj.get_description(),
                "details": "" 
            }
    except Exception as e:
        print(f"Error getting strategy descriptions: {e}")
        # Fallback descriptions
        strategies = {
            "Standard": {"description": "Standard fare calculation", "details": ""},
            "Surge": {"description": "Surge pricing during high demand", "details": ""},
            "Premium": {"description": "Premium service with luxury vehicles", "details": ""}
        }
    return strategies

def get_available_riders_with_status():
    """Get all riders with their availability and active trip status"""
    riders = db.get_all_riders()
    rider_list = []
    
    for rider_row in riders:
        try:
            # users table layout: id, name, rating, role, created_at, vehicle_type, license_plate
            rider_id, name, rating, role, created_at, vehicle_type, license_plate = rider_row
            
            # Skip riders with invalid data
            if not name or not name.strip():
                print(f"Skipping rider with empty name: ID {rider_id}")
                continue
                
            # Check if rider has active trip
            active_trip = db.get_active_trip_for_rider(rider_id)
            
            rider_info = {
                "id": rider_id,
                "name": name.strip(),
                "rating": float(rating) if rating else 4.0,
                "created_at": created_at,
                "available": active_trip is None,
                "active_trip": active_trip,  # Full trip data if exists
                "active_trip_status": active_trip[6] if active_trip else None,  # Trip status
                "active_trip_id": active_trip[0] if active_trip else None  # Trip ID
            }
            rider_list.append(rider_info)
        except Exception as e:
            print(f"Error processing rider row {rider_row}: {e}")
            continue
    
    return rider_list

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

def get_fare_estimate(pickup: str, destination: str, strategy: str, rider_id: int = None) -> dict:
    """Get fare estimate with strategy details for preview using real map data"""
    try:
        # Import here to avoid circular dependency
        from fare_decorators import RiderRatingDecorator
        
        # Create strategy instance to get details
        fare_strategy = FareStrategyFactory.create_strategy(strategy)
        
        # Apply rider rating decorator if rider is selected
        if rider_id:
            rider_record = db.get_user_by_id(rider_id)
            if rider_record:
                rider_rating = float(rider_record[2])  # rating is at index 2
                fare_strategy = RiderRatingDecorator(fare_strategy, rider_rating)
        
        # Get real route data from map service
        route_info = map_service.calculate_trip_route(pickup, destination)
        
        if route_info:
            distance = route_info["distance_km"]
            duration = route_info["duration_min"]
            
            # Store route coordinates for map display
            pickup_coords = route_info["pickup_coords"]
            dest_coords = route_info["destination_coords"]
        else:
            # Fallback to estimation if map service fails
            print(f"Map service failed, using fallback estimation")
            distance = estimate_distance(pickup, destination)
            duration = estimate_eta(pickup, destination)
            pickup_coords = None
            dest_coords = None
        
        # Calculate fare using the decorated strategy
        fare = fare_strategy.calculate_fare(distance, duration)
        
        return {
            "fare": fare,
            "strategy_name": fare_strategy.get_strategy_name(),
            "strategy_description": fare_strategy.get_description(),
            "distance_km": distance,
            "duration_min": duration,
            "pickup_coords": pickup_coords,
            "dest_coords": dest_coords,
            "breakdown": {
                "base_fare": getattr(fare_strategy._wrapped_strategy if hasattr(fare_strategy, '_wrapped_strategy') else fare_strategy, 'BASE_FARE', 0),
                "per_km_rate": getattr(fare_strategy._wrapped_strategy if hasattr(fare_strategy, '_wrapped_strategy') else fare_strategy, 'PER_KM_RATE', 0),
                "per_minute_rate": getattr(fare_strategy._wrapped_strategy if hasattr(fare_strategy, '_wrapped_strategy') else fare_strategy, 'PER_MINUTE_RATE', 0),
                "surge_multiplier": getattr(fare_strategy._wrapped_strategy if hasattr(fare_strategy, '_wrapped_strategy') else fare_strategy, 'SURGE_MULTIPLIER', 1.0)
            }
        }
    except Exception as e:
        print(f"Error calculating fare estimate: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to default values
        return {
            "fare": 10.0,
            "strategy_name": strategy,
            "strategy_description": f"{strategy} fare calculation",
            "distance_km": 5.0,
            "duration_min": 10.0,
            "pickup_coords": None,
            "dest_coords": None,
            "breakdown": {}
        }
    
def estimate_distance(pickup: str, destination: str) -> float:
    """Calculate distance using map service API"""
    try:
        print(f"DEBUG: Calculating distance from '{pickup}' to '{destination}'")
        route_info = map_service.calculate_trip_route(
            pickup_address=pickup, 
            destination_address=destination
        )
        print(f"DEBUG: Route info received: {route_info}")
        if route_info and 'distance_km' in route_info:
            distance = float(route_info['distance_km'])
            print(f"DEBUG: Distance calculated: {distance} km")
            return distance
        else:
            print("DEBUG: Route info missing or invalid")
    except Exception as e:
        print(f"Error getting distance: {e}")
        import traceback
        traceback.print_exc()
    
    # Fallback to default if API fails
    print("DEBUG: Using fallback distance of 5.0 km")
    return 5.0

def estimate_eta(pickup: str, destination: str) -> float:
    """Calculate duration using map service API"""
    try:
        print(f"DEBUG: Calculating ETA from '{pickup}' to '{destination}'")
        route_info = map_service.calculate_trip_route(
            pickup_address=pickup, 
            destination_address=destination
        )
        print(f"DEBUG: Route info received: {route_info}")
        if route_info and 'duration_min' in route_info:
            duration = float(route_info['duration_min'])
            print(f"DEBUG: Duration calculated: {duration} min")
            return duration
        else:
            print("DEBUG: Route info missing or invalid")
    except Exception as e:
        print(f"Error getting duration: {e}")
        import traceback
        traceback.print_exc()
    
    # Fallback to default if API fails
    print("DEBUG: Using fallback duration of 10.0 min")
    return 10.0

def create_trip_with_objects(pickup: str, destination: str, strategy: str, rider: Optional["Rider"] = None) -> Trip:
  """Create a Trip object with full trip_management.py integration including Observer pattern.

  Notes:
  - If a Rider instance is provided, it will be used.
  - If no Rider is provided, this function will try to build one from the Flask
    session (key: 'user_id') or fall back to a lightweight guest Rider.
  - Fully utilizes Trip class from trip_management.py with Observer pattern.
  - Leverages Trip object state management and fare calculation.
  """
  # If caller didn't pass a Rider, try to resolve from session / DB, otherwise use a guest
  if rider is None:
    user_id = None
    try:
      user_id = session.get("user_id")
    except Exception:
      user_id = None

    if user_id:
      # Try to fetch a persistent user record if the DB helper exists.
      try:
        user_record = db.get_user_by_id(user_id)
      except Exception:
        user_record = None

      if user_record:
        # users table layout: id, name, rating, role, created_at, vehicle_type, license_plate
        # Map database fields to Rider constructor parameters
        db_id, db_name, db_rating, db_role, db_created_at, vehicle_type, license_plate = user_record
        # Generate email from name (since DB doesn't have email field)
        email = f"{db_name.lower().replace(' ', '').replace('-', '')}@example.com" if db_name else "user@example.com"
        # Use empty phone since DB doesn't have phone field
        phone = ""
        
        rider = Rider(user_id=str(db_id), name=db_name, email=email, phone=phone)
      else:
        # User ID exists in session but not found in DB
        rider = Rider(user_id=str(user_id), name="Guest User", email="guest@example.com", phone="")
    else:
      # No user_id in session - create guest rider
      rider = Rider(user_id="guest", name="Guest", email="guest@example.com", phone="")

  # Create trip object using Trip class from trip_management.py
  trip = Trip(pickup, destination, rider, strategy)
  
  # OBSERVER PATTERN INTEGRATION:
  # Attach the Rider as an observer to the Trip so they receive state change notifications
  trip.attach(rider)
  print(f"[Observer Pattern] Attached rider {rider.name} as observer to trip {trip.trip_id}")
  
  # Create additional observer for logging state changes
  class TripStateLogger:
    def update(self, trip_obj, old_state, new_state):
      print(f"[Trip State] Trip {trip_obj.trip_id} transitioned: {old_state.value} → {new_state.value}")
  
  logger = TripStateLogger()
  trip.attach(logger)

  # Set route info using map service for more accurate data
  try:
    route_info = map_service.calculate_trip_route(pickup, destination)
    if route_info:
      distance = route_info["distance_km"]
      duration = route_info["duration_min"]
    else:
      # Fallback to estimation
      distance = estimate_distance(pickup, destination)
      duration = estimate_eta(pickup, destination)
  except Exception as e:
    print(f"Error getting route info in create_trip_with_objects: {e}")
    distance = estimate_distance(pickup, destination)
    duration = estimate_eta(pickup, destination)
  
  # Use Trip object's set_route_info method to calculate fare using Strategy pattern
  trip.set_route_info(distance, duration)
  print(f"[Trip Management] Trip {trip.trip_id} created with fare ${trip.base_fare:.2f} using {trip.fare_strategy.get_strategy_name()} strategy")

  return trip

def create_trip_from_database(trip_id: int) -> Optional[Trip]:
    """Create a Trip object from database data with full trip_management.py integration"""
    try:
        # Get trip data from database
        row = db.get_trip_by_id(trip_id)
        if not row:
            print(f"Trip {trip_id} not found in database")
            return None
        
        # Extract trip data
        # trips table: id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id
        trip_db_id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id = row
        
        # Create Rider object from user_id
        rider = create_rider_from_user_id(user_id) if user_id else Rider(user_id="guest", name="Guest", email="guest@example.com", phone="")
        
        # Create Trip object using trip_management.py
        trip = Trip(pickup, destination, rider, strategy)
        trip.trip_id = trip_db_id  # Use database ID
        
        # Set up Observer pattern
        trip.attach(rider)
        
        # Set current state from database
        state_mapping = {
            "requested": TripState.REQUESTED,
            "accepted": TripState.ACCEPTED,
            "in_progress": TripState.IN_PROGRESS,
            "completed": TripState.COMPLETED,
            "declined": TripState.DECLINED,
            "cancelled": TripState.CANCELLED
        }
        
        if state in state_mapping:
            trip._state = state_mapping[state]
        
        # Set route information if available
        if distance and isinstance(distance, (int, float)):
            # Calculate duration from distance (rough estimate)
            duration = distance * 2  # Rough estimate: 2 minutes per km
            trip.set_route_info(float(distance), duration)
        
        print(f"[Trip Management] Reconstructed Trip {trip.trip_id} from database with state {trip.state.value}")
        
        return trip
        
    except Exception as e:
        print(f"Error creating Trip object from database for trip {trip_id}: {e}")
        return None

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
    .flash { margin: 1rem 0; padding: 1rem; border-radius: 8px; }
    .flash.success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
    .flash.error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
    .flash.info { background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; }
  </style>
</head>
<body>
  <main class="container">
    <!-- Flash Messages -->
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    
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
    <p class="muted">Select a rider, then enter pickup and destination to request a trip.</p>

    <!-- Rider Selection Section -->
    <section class="card" style="margin-bottom: 1rem;">
        <h3 style="margin-top: 0;">Select Rider</h3>
        
        {% if available_riders %}
        <form method="POST" action="{{ url_for('rider_home.home') }}">
            <label>
                Choose Rider
                <select name="selected_rider_id" onchange="this.form.submit()" required>
                    <option value="">-- Select a Rider --</option>
                    {% for rider in available_riders %}
                        <option value="{{ rider.id }}" 
                                {% if selected_rider and selected_rider.id == rider.id %}selected{% endif %}>
                            {{ rider.name }} (★{{ "%.1f"|format(rider.rating) }})
                            {% if not rider.available %}
                                - ON TRIP ({{ get_status_label(rider.active_trip_status) }})
                            {% endif %}
                        </option>
                    {% endfor %}
                </select>
            </label>
            <input type="hidden" name="action" value="select_rider">
        </form>
        
        <div style="margin-top: 1rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <a role="button" href="{{ url_for('rider_home.create_rider') }}" class="secondary" style="font-size: 0.9rem;">
                + Add New Rider
            </a>
            {% if available_riders|length < 3 %}
            <form method="POST" action="{{ url_for('rider_home.create_demo_riders') }}" style="display: inline;">
                <button type="submit" class="secondary" style="font-size: 0.9rem;">+ Add Demo Riders</button>
            </form>
            {% endif %}
        </div>
        
        {% else %}
        <!-- No riders exist - show creation options -->
        <div style="text-align: center; padding: 2rem; background: #f8f9fa; border-radius: 8px;">
            <h4 style="margin: 0 0 1rem 0; color: #666;">No Riders Found</h4>
            <p style="margin: 0 0 1.5rem 0; color: #666;">
                There are no riders in the system yet. Create your first rider to get started.
            </p>
            <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
                <a role="button" href="{{ url_for('rider_home.create_rider') }}">
                    + Create New Rider
                </a>
                <form method="POST" action="{{ url_for('rider_home.create_demo_riders') }}" style="display: inline;">
                    <button type="submit" class="secondary">+ Add Demo Riders</button>
                </form>
            </div>
        </div>
        {% endif %}
        
        {% if selected_rider %}
            <div style="margin-top: 1rem; padding: 1rem; border-radius: 8px; border-left: 4px solid #4CAF50; {% if selected_rider.available %}background: #e8f5e8;{% else %}background: #fff3cd; border-left-color: #ffc107;{% endif %}">
                <strong>Selected Rider:</strong> {{ selected_rider.name }} 
                <span style="color: #666;">(★{{ "%.1f"|format(selected_rider.rating) }}, Member since {{ selected_rider.created_at[:10] }})</span>
                {% if not selected_rider.available %}
                    <div style="color: #856404; margin-top: 0.5rem;">
                        🚗 <strong>Currently on trip ({{ get_status_label(selected_rider.active_trip_status) }})</strong>
                        <br>Manage current trip below or select a different rider to request a new trip.
                    </div>
                {% endif %}
            </div>
        {% endif %}
    </section>

    <!-- Active Trip Management (shown if rider has active trip) -->
    {% if selected_rider and not selected_rider.available %}
    <section class="card">
        <h3 style="margin-top: 0;">🚗 Active Trip for {{ selected_rider.name }}</h3>
        
        {% if selected_rider.active_trip %}
            <div style="background: #f8f9fa; padding: 1rem; border-radius: 6px; margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <strong>Trip #{{ selected_rider.active_trip_id }}</strong>
                    <span class="pill" style="background: #007bff; color: white;">{{ get_status_label(selected_rider.active_trip_status) }}</span>
                </div>
                
                <p style="margin: 0.25rem 0;"><strong>Pickup:</strong> {{ selected_rider.active_trip[2] }}</p>
                <p style="margin: 0.25rem 0;"><strong>Destination:</strong> {{ selected_rider.active_trip[3] }}</p>
                <p style="margin: 0.25rem 0;"><strong>Fare:</strong> ${{ "%.2f"|format(selected_rider.active_trip[5]) }}</p>
                <p style="margin: 0.25rem 0;"><strong>Strategy:</strong> {{ selected_rider.active_trip[4] }}</p>
            </div>
            
            <div class="actions">
                <a role="button" href="{{ url_for('rider_home.live_trip', trip_id=selected_rider.active_trip_id) }}" class="primary">
                    📱 View Live Trip
                </a>
                <a role="button" href="{{ url_for('rider_home.trip_summary', trip_id=selected_rider.active_trip_id) }}" class="secondary">
                    📋 Trip Details
                </a>
            </div>
            
            <p class="muted" style="margin-top: 1rem;">
                💡 You can track your trip progress, contact your driver, or cancel the trip using the Live Trip view.
                Once this trip is completed, you'll be able to request new trips.
            </p>
        {% endif %}
    </section>
    
    <!-- Trip Request Form (only shown if rider selected and available) -->
    {% elif selected_rider and selected_rider.available %}
    <section class="card">
        <h3 style="margin-top: 0;">Request Trip for {{ selected_rider.name }}</h3>
        <form method="POST" action="{{ url_for('rider_home.home') }}">
            <input type="hidden" name="selected_rider_id" value="{{ selected_rider.id }}">
            
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
                <select name="strategy" onchange="updateStrategyInfo(this.value)">
                    {% for s in available_strategies %}
                        <option value="{{ s }}" {% if s == strategy %}selected{% endif %}>{{ s }}</option>
                    {% endfor %}
                </select>
                <div id="strategy-info" style="margin-top: 0.5rem; padding: 0.5rem; background: #f8f9fa; border-radius: 4px; font-size: 0.9rem; color: #666;">
                    <span id="strategy-description">Select a strategy to see pricing details</span>
                </div>
            </label>

            <script>
                // Strategy descriptions (loaded from Python)
                const strategyInfo = {
                    {% for s in available_strategies %}
                    "{{ s }}": {
                        description: "{{ strategy_descriptions.get(s, {}).get('description', s + ' fare calculation') }}",
                        details: "{{ strategy_descriptions.get(s, {}).get('details', '') }}"
                    },
                    {% endfor %}
                };

                function updateStrategyInfo(strategy) {
                    const info = strategyInfo[strategy];
                    const descElement = document.getElementById('strategy-description');
                    if (info && descElement) {
                        descElement.innerHTML = `<strong>${strategy}:</strong> ${info.description}${info.details ? '<br><small>' + info.details + '</small>' : ''}`;
                    }
                }

                // Initialize on page load
                document.addEventListener('DOMContentLoaded', function() {
                    const strategySelect = document.querySelector('select[name="strategy"]');
                    if (strategySelect) {
                        updateStrategyInfo(strategySelect.value);
                    }
                });
            </script>

            <div class="actions">
                <button type="submit" name="action" value="preview" class="contrast">Preview Route &amp; Fare</button>
                <button type="submit" name="action" value="request">Request Trip</button>
                <a role="button" href="{{ url_for('rider_home.past_trips') }}" class="secondary">View Past Trips</a>
            </div>
        </form>
    </section>
    {% else %}
    <!-- Message when no rider is selected -->
    <section class="card">
        <h3 style="color: #666;">No Rider Selected</h3>
        <p style="color: #666;">Please select a rider from the dropdown above to continue with trip planning.</p>
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

  <p style="margin:.25rem 0;"><strong>Estimated ETA:</strong> {{ "%.1f"|format(eta_min) }} minutes</p>
  <p style="margin:.25rem 0;"><strong>Estimated Distance:</strong> {{ "%.1f"|format(distance_km) }} km</p>
  <p style="margin:.25rem 0;"><strong>Strategy Description:</strong> {{ strategy_description }}</p>
  
  <div style="border-left: 3px solid #4CAF50; padding-left: 1rem; margin: 1rem 0;">
    <h4 style="margin: 0 0 0.5rem 0; color: #4CAF50;">Estimated Fare: ${{ "%.2f"|format(fare) }}</h4>
    
    {% if breakdown %}
    <details>
      <summary style="cursor: pointer; color: #666;">View fare breakdown</summary>
      <div style="margin-top: 0.5rem; font-size: 0.9rem;">
        {% if breakdown.base_fare %}
        <p style="margin: 0.2rem 0;">Base fare: ${{ "%.2f"|format(breakdown.base_fare) }}</p>
        {% endif %}
        {% if breakdown.per_km_rate %}
        <p style="margin: 0.2rem 0;">Distance ({{ "%.1f"|format(distance_km) }} km × ${{ "%.2f"|format(breakdown.per_km_rate) }}): ${{ "%.2f"|format(distance_km * breakdown.per_km_rate) }}</p>
        {% endif %}
        {% if breakdown.per_minute_rate %}
        <p style="margin: 0.2rem 0;">Time ({{ "%.0f"|format(eta_min) }} min × ${{ "%.2f"|format(breakdown.per_minute_rate) }}): ${{ "%.2f"|format(eta_min * breakdown.per_minute_rate) }}</p>
        {% endif %}
        {% if breakdown.surge_multiplier and breakdown.surge_multiplier > 1.0 %}
        <p style="margin: 0.2rem 0; color: #f44336;">Surge multiplier: {{ "%.1f"|format(breakdown.surge_multiplier) }}×</p>
        {% endif %}
      </div>
    </details>
    {% endif %}
  </div>
</section>

<section class="card" style="margin-top:1rem;">
  <h3 style="margin-top:0;">Route Preview</h3>
  <div class="map">{{ fmap|safe }}</div>
  <p class="muted" style="margin-top:.5rem;">
    {% if pickup_coords and dest_coords %}
      Interactive map showing the route from pickup to destination with markers and route line.
    {% else %}
      Map preview using estimated location. For real coordinates, ensure addresses are valid and map service is available.
    {% endif %}
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
  <a href="{{ url_for('rider_home.past_trips') }}" class="secondary">Back to Past Trips</a>
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
  <a href="{{ url_for('rider_home.past_trips') }}" class="secondary">Past Trips</a>
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
  <a href="{{ url_for('rider_home.past_trips') }}" class="secondary">Past Trips</a>
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
      Live trip map showing pickup and destination locations with route visualization.
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
    selected_rider = None
    selected_rider_id = None

    # Get available riders
    available_riders = get_available_riders_with_status()

    if request.method == "POST":
        selected_rider_id = request.form.get("selected_rider_id")
        pickup = request.form.get("pickup", "").strip()
        destination = request.form.get("destination", "").strip()
        strategy = request.form.get("strategy", "Standard")
        action = request.form.get("action")

        # Find selected rider from available riders
        if selected_rider_id and selected_rider_id.isdigit():
            selected_rider_id = int(selected_rider_id)
            for rider in available_riders:
                if rider["id"] == selected_rider_id:
                    selected_rider = rider
                    break

        if action == "select_rider":
            # Just selecting a rider, refresh page with rider selected
            pass
            
        elif action == "preview":
            # Validate rider selection and availability
            if not selected_rider:
                flash("Please select a rider first.", "error")
                return redirect(url_for("rider_home.home"))
            
            if not selected_rider["available"]:
                flash(f"Selected rider {selected_rider['name']} has an active trip. Please select a different rider.", "error")
                return redirect(url_for("rider_home.home"))
            
            # Use integrated fare calculation for preview WITH RIDER RATING DECORATOR
            fare_estimate = get_fare_estimate(pickup, destination, strategy, rider_id=selected_rider_id)
            
            # Create enhanced map with route visualization
            pickup_coords = fare_estimate.get("pickup_coords")
            dest_coords = fare_estimate.get("dest_coords")
            fmap_html = make_map(pickup_coords, dest_coords)

            body = render_template_string(
                PREVIEW_BODY,
                pickup=pickup,
                destination=destination,
                strategy=strategy,
                distance_km=fare_estimate["distance_km"],
                eta_min=fare_estimate["duration_min"],
                fare=fare_estimate["fare"],
                strategy_description=fare_estimate["strategy_description"],
                breakdown=fare_estimate["breakdown"],
                pickup_coords=pickup_coords,
                dest_coords=dest_coords,
                fmap=fmap_html
            )

            return render_template_string(BASE_HTML, body=body)
        
        elif action == "confirm":
            # Confirm from Trip Preview page: validate rider and create trip using full Trip object integration
            if not selected_rider or not selected_rider["available"]:
                flash("Cannot create trip: rider not available.", "error")
                return redirect(url_for("rider_home.home"))
                
            # Create rider object and Trip object with full trip_management.py integration
            rider = create_rider_from_user_id(selected_rider_id)
            trip_obj = create_trip_with_objects(pickup, destination, strategy, rider)
            
            # Save to database using Trip object properties
            trip_id = db.create_trip(pickup, destination, strategy, trip_obj.base_fare, selected_rider_id)
            
            # Store Trip object ID mapping for future reference
            if trip_id:
                trip_obj.trip_id = trip_id
                print(f"[Trip Management] Created trip {trip_id} with Trip object {trip_obj.trip_id}, state: {trip_obj.state.value}")
            
            flash(f"Trip successfully requested for {selected_rider['name']} using Trip object (${trip_obj.base_fare:.2f})!", "success")
            return redirect(url_for("rider_home.past_trips"))
            
        elif action == "cancel":
            # From Trip Preview: just go back to clean Rider Home
            return redirect(url_for("rider_home.home"))
            
        elif action == "request":
            # Validate rider selection and availability
            if not selected_rider:
                flash("Please select a rider first.", "error")
                return redirect(url_for("rider_home.home"))
            
            if not selected_rider["available"]:
                flash(f"Cannot request trip: {selected_rider['name']} has an active trip ({get_status_label(selected_rider['active_trip_status'])}).", "error")
                return redirect(url_for("rider_home.home"))
            
            # Create rider object and Trip object with full trip_management.py integration
            rider = create_rider_from_user_id(selected_rider_id)
            trip_obj = create_trip_with_objects(pickup, destination, strategy, rider)
            
            # Save to database using Trip object properties and state
            trip_id = db.create_trip(pickup, destination, strategy, trip_obj.base_fare, selected_rider_id)
            
            # Update Trip object with database ID
            if trip_id:
                trip_obj.trip_id = trip_id
                print(f"[Trip Management] Direct request: Created trip {trip_id} with Trip object, initial state: {trip_obj.state.value}")
                print(f"[Trip Management] Trip details: {trip_obj}")
            
            flash(f"Trip successfully requested for {selected_rider['name']} using Trip object (${trip_obj.base_fare:.2f}, {trip_obj.fare_strategy.get_strategy_name()})!", "success")
            return redirect(url_for("rider_home.past_trips"))
    
    # Get available strategies from FareStrategyFactory
    available_strategies = FareStrategyFactory.get_available_strategies()
    strategy_descriptions = get_strategy_descriptions()

    # Create map with coordinates if pickup and destination are provided
    pickup_coords = None
    dest_coords = None
    if pickup and destination:
        try:
            route_info = map_service.calculate_trip_route(pickup, destination)
            if route_info:
                pickup_coords = route_info["pickup_coords"]
                dest_coords = route_info["destination_coords"]
        except Exception as e:
            print(f"Could not get route coordinates for home map: {e}")
    
    fmap_html = make_map(pickup_coords, dest_coords)
    body = render_template_string(
        HOME_BODY,
        pickup=pickup,
        destination=destination,
        strategy=strategy,
        available_strategies=available_strategies,
        strategy_descriptions=strategy_descriptions,
        available_riders=available_riders,
        selected_rider=selected_rider,
        fmap=fmap_html,
        get_status_label=get_status_label
    )

    return render_template_string(BASE_HTML, body=body)

@rider_home.route("/create-rider", methods=["GET", "POST"])
def create_rider():
    """Route for creating new riders"""
    
    if request.method == "POST":
        rider_name = request.form.get("rider_name", "").strip()
        rider_rating = request.form.get("rider_rating", "4.0")
        
        if not rider_name:
            flash("Rider name is required.", "error")
        elif len(rider_name) < 2:
            flash("Rider name must be at least 2 characters long.", "error")
        else:
            try:
                # Validate rating
                rating_float = float(rider_rating)
                if rating_float < 1.0 or rating_float > 5.0:
                    flash("Rating must be between 1.0 and 5.0.", "error")
                else:
                    # Create the rider
                    rider_id = db.create_user(rider_name, str(rating_float), "rider")
                    flash(f"Successfully created rider: {rider_name} (★{rating_float})", "success")
                    return redirect(url_for("rider_home.home"))
            except ValueError:
                flash("Invalid rating format. Please use numbers like 4.5", "error")
            except Exception as e:
                flash(f"Error creating rider: {str(e)}", "error")
    
    create_rider_body = """
    <nav>
        <a href="{{ url_for('rider_home.home') }}" class="secondary">Back to Rider Home</a>
        <a href="{{ url_for('driver_home.home') }}" class="secondary">Driver Home</a>
    </nav>

    <h2>Create New Rider</h2>
    <p class="muted">Add a new rider to the system.</p>

    <section class="card">
        <h3 style="margin-top: 0;">Rider Information</h3>
        <form method="POST" action="{{ url_for('rider_home.create_rider') }}">
            <label>
                Rider Name *
                <input type="text" name="rider_name" placeholder="e.g., John Smith" required 
                       value="{{ request.form.get('rider_name', '') }}" maxlength="100">
                <small>Enter the full name of the rider</small>
            </label>

            <label>
                Initial Rating
                <select name="rider_rating">
                    <option value="5.0" {% if request.form.get('rider_rating') == '5.0' %}selected{% endif %}>★★★★★ 5.0 - Excellent</option>
                    <option value="4.5" {% if request.form.get('rider_rating', '4.0') == '4.5' %}selected{% endif %}>★★★★☆ 4.5 - Very Good</option>
                    <option value="4.0" {% if request.form.get('rider_rating', '4.0') == '4.0' %}selected{% endif %}>★★★★☆ 4.0 - Good</option>
                    <option value="3.5" {% if request.form.get('rider_rating') == '3.5' %}selected{% endif %}>★★★☆☆ 3.5 - Average</option>
                    <option value="3.0" {% if request.form.get('rider_rating') == '3.0' %}selected{% endif %}>★★★☆☆ 3.0 - Fair</option>
                </select>
                <small>New riders typically start with a 4.0 rating</small>
            </label>

            <div class="actions">
                <button type="submit">Create Rider</button>
                <a role="button" href="{{ url_for('rider_home.home') }}" class="secondary">Cancel</a>
            </div>
        </form>
    </section>

    <section class="card" style="margin-top: 1rem;">
        <h3 style="margin-top: 0;">Quick Add Demo Riders</h3>
        <p class="muted">Need some sample riders for testing? Click below to add demo riders.</p>
        
        <form method="POST" action="{{ url_for('rider_home.create_demo_riders') }}" style="display: inline;">
            <button type="submit" class="secondary">Add Demo Riders</button>
        </form>
        
        <small style="color: #666; margin-left: 1rem;">
            This will create 5 sample riders with different ratings
        </small>
    </section>
    """
    
    body = render_template_string(create_rider_body)
    return render_template_string(BASE_HTML, body=body)

@rider_home.route("/create-demo-riders", methods=["POST"])
def create_demo_riders():
    """Create demo riders for testing"""
    
    demo_riders = [
        ("Alice Johnson", "4.9"),
        ("Michael Chen", "4.7"), 
        ("Sarah Williams", "4.5"),
        ("David Rodriguez", "4.2"),
        ("Emily Davis", "4.8")
    ]
    
    created_count = 0
    
    for name, rating in demo_riders:
        try:
            db.create_user(name, rating, "rider")
            created_count += 1
        except Exception as e:
            print(f"Error creating demo rider {name}: {e}")
    
    if created_count > 0:
        flash(f"Successfully created {created_count} demo riders!", "success")
    else:
        flash("Error creating demo riders. They may already exist.", "error")
    
    return redirect(url_for("rider_home.home"))


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
        
        # Get driver info and convert to dictionary
        driver_row = get_driver_for_trip(trip_id)
        driver = None
        if driver_row:
            try:
                # The JOIN query returns: users table + trips table
                # users: id, name, rating, role, created_at, vehicle_type, license_plate  
                # trips: id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id
                driver = {
                    "name": driver_row[1] if len(driver_row) > 1 else "Unknown Driver",
                    "rating": float(driver_row[2]) if len(driver_row) > 2 and driver_row[2] else 4.0,
                    "vehicle_color": "Blue",  # Mock data since not in DB
                    "vehicle_model": driver_row[5] if len(driver_row) > 5 and driver_row[5] else "Toyota Prius",
                    "vehicle_plate": driver_row[6] if len(driver_row) > 6 and driver_row[6] else "ABC123",
                    "eta_min": 5  # Mock ETA
                }
            except Exception as e:
                print(f"Error processing driver data: {e}")
                # Fallback driver info
                driver = {
                    "name": "Unknown Driver",
                    "rating": 4.0,
                    "vehicle_color": "Blue",
                    "vehicle_model": "Toyota Prius", 
                    "vehicle_plate": "ABC123",
                    "eta_min": 5
                }

        if request.method == "POST":
            action = request.form.get("action")

            if action == "contact":
                # UI-only: pretend we're opening a chat/call
                banner = {
                    "title": "Contacting driver…",
                    "detail": "This is a demo. In a real app, this would open in-app chat or call.",
                }
            elif action == "cancel" and trip["state"] not in ["completed", "cancelled"]:
                # TRIP MANAGEMENT INTEGRATION:
                # Use Trip object from trip_management.py for proper state management
                try:
                    trip_obj = create_trip_from_database(trip_id)
                    if trip_obj:
                        # Trip object handles state change and notifies observers
                        old_state = trip_obj.state
                        
                        # Create a cancellation state transition (Trip class doesn't have cancel method)
                        # So we'll use _change_state directly to go to CANCELLED
                        trip_obj._change_state(TripState.CANCELLED)
                        
                        print(f"[Trip Management] Trip {trip_id} cancelled using Trip object: {old_state.value} → {trip_obj.state.value}")
                        
                        # Update database to reflect Trip object state
                        db.update_trip_status(trip_id, "cancelled")
                        trip["state"] = "cancelled"
                        trip["status_label"] = status_map["cancelled"]
                        
                        banner = {
                            "title": "Trip Cancelled (Trip Management)",
                            "detail": "Trip cancelled using Trip object state management with Observer notifications.",
                        }
                    else:
                        # Fallback to direct database update if Trip object creation fails
                        print(f"Failed to create Trip object for cancellation, using fallback")
                        db.update_trip_status(trip_id, "cancelled")
                        trip["state"] = "cancelled"
                        trip["status_label"] = status_map["cancelled"]
                        
                        banner = {
                            "title": "Trip Cancelled",
                            "detail": "Your trip has been cancelled.",
                        }
                        
                except Exception as e:
                    print(f"Error using Trip object for cancellation: {e}")
                    # Fallback to direct database update
                    db.update_trip_status(trip_id, "cancelled")
                    trip["state"] = "cancelled"
                    trip["status_label"] = status_map["cancelled"]
                    
                    banner = {
                        "title": "Trip Cancelled",
                        "detail": "Your trip has been cancelled.",
                    }
        
        # Try to get route coordinates for enhanced map display
        pickup_coords = None
        dest_coords = None
        try:
            route_info = map_service.calculate_trip_route(trip["pickup"], trip["destination"])
            if route_info:
                pickup_coords = route_info["pickup_coords"]
                dest_coords = route_info["destination_coords"]
        except Exception as e:
            print(f"Could not get route coordinates for live trip: {e}")
        
        fmap_html = make_map(pickup_coords, dest_coords)

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

@rider_home.route("/advanced-trip", methods=["GET", "POST"])
def advanced_trip():
    """Demonstrate advanced Trip object functionality with Observer pattern"""
    if request.method == "POST":
        pickup = request.form.get("pickup", "").strip()
        destination = request.form.get("destination", "").strip()
        strategy = request.form.get("strategy", "Standard")
        action = request.form.get("action")
        
        if action == "create_advanced_trip":
            # Create Trip object with full OOP patterns
            trip_obj = create_trip_with_objects(pickup, destination, strategy)
            
            # Save to database using new helper function
            trip_id = db.create_trip_from_object(trip_obj)
            
            # Create a simple observer for demonstration
            class TripLogger:
                def update(self, trip, old_state, new_state):
                    print(f"Trip {trip.trip_id} changed from {old_state.value} to {new_state.value}")
            
            logger = TripLogger()
            trip_obj.attach(logger)
            
            # Simulate trip progression
            if strategy == "Premium":
                # Create a mock driver and accept the trip
                driver = Driver(user_id=2, name="John Driver", email="driver@example.com", 
                              vehicle_info="Toyota Prius", license_plate="ABC123")
                trip_obj.accept(driver)
                db.update_trip_from_object(trip_id, trip_obj)
            
            return redirect(url_for("rider_home.trip_details", trip_id=trip_id))
    
    advanced_trip_body = """
    <nav>
        <a href="{{ url_for('rider_home.home') }}" class="secondary">Back to Rider Home</a>
    </nav>
    
    <h2>Advanced Trip Management</h2>
    <p class="muted">Demonstration of Trip object with Observer and Strategy patterns</p>
    
    <section class="card">
        <h3>Create Trip with OOP Patterns</h3>
        <form method="POST">
            <div class="grid-2">
                <label>
                    Pickup Address
                    <input type="text" name="pickup" placeholder="e.g., 350 5th Ave, New York, NY" required>
                </label>
                <label>
                    Destination Address
                    <input type="text" name="destination" placeholder="e.g., Times Square, New York, NY" required>
                </label>
            </div>
            
            <label>
                Fare Strategy (affects calculation algorithm)
                <select name="strategy">
                    <option value="Standard">Standard - Basic rates</option>
                    <option value="Surge">Surge - High demand multiplier</option>
                    <option value="Premium">Premium - Luxury service (auto-accept demo)</option>
                </select>
            </label>
            
            <button type="submit" name="action" value="create_advanced_trip">
                Create Trip with Advanced Features
            </button>
        </form>
        
        <p class="muted" style="margin-top:1rem;">
            This demonstrates comprehensive <strong>trip_management.py</strong> integration:<br>
            • <strong>Observer Pattern:</strong> Riders, drivers, and analytics automatically receive notifications when trip state changes<br>
            • <strong>Strategy Pattern:</strong> Different fare calculation algorithms (Standard, Surge, Premium) using FareStrategy classes<br>
            • <strong>State Management:</strong> Trip objects manage their own state using TripState enum with proper transitions<br>
            • <strong>Database Synchronization:</strong> Trip objects sync seamlessly with database while maintaining object state<br>
            • <strong>Premium Demo:</strong> Premium trips show complete lifecycle: REQUESTED → ACCEPTED → IN_PROGRESS<br>
            • <strong>Fare Calculation:</strong> Automatic fare calculation using distance, duration, and strategy pattern<br>
            • <strong>Observer Logging:</strong> Real-time console output shows Observer pattern and Trip object interactions
        </p>
    </section>
    """
    
    body = render_template_string(advanced_trip_body)
    return render_template_string(BASE_HTML, body=body)

@rider_home.route("/trip-details/<int:trip_id>")
def trip_details(trip_id):
    """Show detailed trip information with comprehensive Trip object integration from trip_management.py"""
    # Get database record
    row = db.get_trip_by_id(trip_id)
    if not row:
        return "Trip not found", 404
    
    trip_data = {
        "id": row[0],
        "created_at": row[1], 
        "pickup": row[2],
        "destination": row[3],
        "strategy": row[4],
        "fare": row[5],
        "state": row[6],
        "distance": row[7] if len(row) > 7 else 0
    }
    
    # Create Trip object from database for comprehensive integration demo
    trip_obj = create_trip_from_database(trip_id)
    
    if trip_obj:
        trip_details_body = f"""
        <nav>
            <a href="{{ url_for('rider_home.home') }}" class="secondary">Back to Rider Home</a>
            <a href="{{ url_for('rider_home.advanced_trip') }}" class="secondary">Advanced Trip</a>
        </nav>
        
        <h2>Trip Details (Full Trip Management Integration)</h2>
        
        <section class="card">
            <h3>Database Information</h3>
            <p><strong>Trip ID:</strong> {trip_data['id']}</p>
            <p><strong>Created:</strong> {trip_data['created_at']}</p>
            <p><strong>Pickup:</strong> {trip_data['pickup']}</p>
            <p><strong>Destination:</strong> {trip_data['destination']}</p>
            <p><strong>State:</strong> {trip_data['state']}</p>
            <p><strong>Distance:</strong> {trip_data['distance']} km</p>
        </section>
        
        <section class="card" style="margin-top:1rem;">
            <h3>Trip Object Information (trip_management.py)</h3>
            <p><strong>Trip Object ID:</strong> {trip_obj.trip_id}</p>
            <p><strong>Object State:</strong> {trip_obj.state.value} (using TripState enum)</p>
            <p><strong>Strategy Used:</strong> {trip_obj.fare_strategy.get_strategy_name()}</p>
            <p><strong>Strategy Description:</strong> {trip_obj.fare_strategy.get_description()}</p>
            <p><strong>Calculated Fare:</strong> ${trip_obj.base_fare:.2f} (using Strategy pattern)</p>
            <p><strong>Route Info:</strong> {trip_obj.distance_km:.2f} km, {trip_obj.duration_min:.1f} min</p>
            <p><strong>Created At:</strong> {trip_obj.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Attached Observers:</strong> {len(trip_obj._observers)}</p>
            <p><strong>Rider:</strong> {trip_obj.rider.name} ({trip_obj.rider.user_id})</p>
            {f'<p><strong>Driver:</strong> {trip_obj.driver.name}</p>' if trip_obj.driver else '<p><strong>Driver:</strong> Not assigned</p>'}
        </section>
        
        <section class="card" style="margin-top:1rem; background: #f8f9fa;">
            <h3>Trip Object Integration Demo</h3>
            <p class="muted">
                This page demonstrates comprehensive integration with <strong>trip_management.py</strong>:
            </p>
            <div style="background: #fff; padding: 1rem; border-radius: 6px; margin-top: 1rem;">
                <h4 style="margin-top: 0; color: #495057;">Full Trip Object Functionality:</h4>
                <ul style="margin: 0.5rem 0;">
                    <li><strong>Observer Pattern:</strong> Trip object notifies {len(trip_obj._observers)} attached observers of state changes</li>
                    <li><strong>Strategy Pattern:</strong> Fare calculated using {trip_obj.fare_strategy.get_strategy_name()} strategy</li>
                    <li><strong>State Management:</strong> Current state: {trip_obj.state.value} (TripState enum)</li>
                    <li><strong>Automatic Fare Calculation:</strong> ${trip_obj.base_fare:.2f} calculated from {trip_obj.distance_km:.2f} km route</li>
                    <li><strong>Database Synchronization:</strong> Trip object state synced with database</li>
                </ul>
            </div>
            
            <div style="background: #e8f5e8; padding: 1rem; border-radius: 6px; margin-top: 1rem; border-left: 4px solid #28a745;">
                <h4 style="margin-top: 0; color: #28a745;">Trip Object String Representation:</h4>
                <code style="background: #f8f9fa; padding: 0.5rem; border-radius: 4px; display: block;">
                    {str(trip_obj)}
                </code>
            </div>
            
            <p style="margin: 1rem 0 0 0; font-size: 0.9rem; color: #6c757d;">
                💡 This Trip object was reconstructed from database data and includes full Observer pattern integration,
                Strategy pattern fare calculation, and state management from trip_management.py!
            </p>
        </section>
        """
    else:
        # Fallback if Trip object creation fails
        trip_details_body = f"""
        <nav>
            <a href="{{ url_for('rider_home.home') }}" class="secondary">Back to Rider Home</a>
        </nav>
        
        <h2>Trip Details</h2>
        
        <section class="card">
            <h3>Database Information</h3>
            <p><strong>Trip ID:</strong> {trip_data['id']}</p>
            <p><strong>Created:</strong> {trip_data['created_at']}</p>
            <p><strong>Pickup:</strong> {trip_data['pickup']}</p>
            <p><strong>Destination:</strong> {trip_data['destination']}</p>
            <p><strong>State:</strong> {trip_data['state']}</p>
            <p><strong>Fare:</strong> ${trip_data['fare']:.2f}</p>
        </section>
        
        <section class="card" style="margin-top:1rem;">
            <h3>Trip Object Integration</h3>
            <p class="muted">
                Could not create Trip object from database data. This may indicate missing data or configuration issues.
                The Trip object would normally provide Observer pattern integration and Strategy pattern fare calculation.
            </p>
        </section>
        """
    
    body = render_template_string(trip_details_body)
    return render_template_string(BASE_HTML, body=body)
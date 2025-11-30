from flask import Blueprint, render_template_string, request, flash, redirect, url_for
from typing import Optional
import folium
import db
from trip_management import Trip
from user_classes import Rider, Driver, TripState
from fare_calc import FareStrategyFactory
from map_integration import MapService, MockMapService
import os
import time
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

driver_home = Blueprint("driver_home", __name__)

# Initialize map service (use Mock if no API key available)
try:
    if os.getenv("ORS_API_KEY"):
        map_service = MapService()
        print("Driver Home: Using real MapService with OpenRouteService API")
    else:
        map_service = MockMapService()
        print("Driver Home: Using MockMapService (no API key found)")
except Exception as e:
    print(f"Driver Home: Failed to initialize map service: {e}")
    map_service = MockMapService()  # Fallback instance

def invalidate_caches():
    """Invalidate all caches when data changes"""
    global _driver_cache_time, _trip_cache_time
    _driver_cache_time = 0
    _trip_cache_time = 0

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

# Cache for expensive driver queries (cache for 30 seconds)
_driver_cache = {}
_driver_cache_time = 0
_CACHE_TIMEOUT = 30  # seconds

def get_available_drivers_with_status():
    """Get all drivers and their availability status with caching"""
    global _driver_cache, _driver_cache_time
    
    # Check if cache is still valid
    current_time = time.time()
    if current_time - _driver_cache_time < _CACHE_TIMEOUT and _driver_cache:
        return _driver_cache.get('drivers', [])
    
    try:
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
        
        # Update cache
        _driver_cache = {'drivers': driver_list}
        _driver_cache_time = current_time
        
        return driver_list
        
    except Exception as e:
        print(f"Error getting drivers: {e}")
        return _driver_cache.get('drivers', [])

# --------- Enhanced Map helper for driver view ---------
@lru_cache(maxsize=32)
def make_driver_map(trip_pickup=None, trip_destination=None, driver_location=None, trip_status="requested"):
    """Enhanced driver map with trip route and driver position simulation - cached for performance"""
    # Default center (NYC)
    center_lat, center_lon = 40.758, -73.9855
    
    # Try to get real coordinates if addresses are provided (but cache the results)
    pickup_coords = None
    dest_coords = None
    
    if trip_pickup and trip_destination:
        try:
            # Use cached route info to avoid repeated API calls
            route_info = get_trip_route_info(trip_pickup, trip_destination)
            if route_info and route_info["pickup_coords"] and route_info["destination_coords"]:
                pickup_coords = route_info["pickup_coords"]
                dest_coords = route_info["destination_coords"]
                # Center map between pickup and destination
                center_lat = (pickup_coords[0] + dest_coords[0]) / 2
                center_lon = (pickup_coords[1] + dest_coords[1]) / 2
        except Exception as e:
            print(f"Could not get route coordinates for driver map: {e}")
    
    # Create map centered appropriately
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="OpenStreetMap")
    
    # Add pickup marker if available
    if pickup_coords:
        pickup_icon = "play" if trip_status in ["requested", "accepted"] else "check"
        pickup_color = "green" if trip_status in ["completed"] else "orange"
        
        folium.Marker(
            pickup_coords,
            popup=f"Pickup: {trip_pickup}",
            tooltip="Pickup Location",
            icon=folium.Icon(color=pickup_color, icon=pickup_icon)
        ).add_to(fmap)
    
    # Add destination marker if available
    if dest_coords:
        dest_icon = "stop" if trip_status != "completed" else "flag"
        dest_color = "red" if trip_status != "completed" else "green"
        
        folium.Marker(
            dest_coords,
            popup=f"Destination: {trip_destination}",
            tooltip="Destination",
            icon=folium.Icon(color=dest_color, icon=dest_icon)
        ).add_to(fmap)
    
    # Add route line if both points exist
    if pickup_coords and dest_coords:
        route_color = "blue"
        route_opacity = 0.8
        
        if trip_status == "in_progress":
            route_color = "green"
            route_opacity = 0.9
        elif trip_status == "completed":
            route_color = "gray"
            route_opacity = 0.5
        
        folium.PolyLine(
            [pickup_coords, dest_coords],
            weight=5,
            color=route_color,
            opacity=route_opacity,
            popup=f"Route ({trip_status})"
        ).add_to(fmap)
    
    # Add simulated driver position
    if driver_location:
        folium.Marker(
            driver_location,
            popup="Driver Location",
            tooltip="You are here",
            icon=folium.Icon(color="blue", icon="car", prefix="fa")
        ).add_to(fmap)
    elif pickup_coords and trip_status in ["accepted", "in_progress"]:
        # Simulate driver position based on trip status
        if trip_status == "accepted":
            # Driver is heading to pickup - place somewhere between default center and pickup
            driver_lat = (center_lat + pickup_coords[0]) / 2
            driver_lon = (center_lon + pickup_coords[1]) / 2
        else:  # in_progress
            # Driver is en route to destination - place somewhere between pickup and destination
            driver_lat = (pickup_coords[0] + dest_coords[0]) / 2
            driver_lon = (pickup_coords[1] + dest_coords[1]) / 2
        
        folium.Marker(
            [driver_lat, driver_lon],
            popup="Driver Location (Simulated)",
            tooltip="Driver Position",
            icon=folium.Icon(color="blue", icon="car", prefix="fa")
        ).add_to(fmap)
    
    return fmap._repr_html_()

@lru_cache(maxsize=128)
def get_trip_route_info(pickup_address: str, destination_address: str):
    """Get route information for a trip to enhance driver navigation with caching"""
    try:
        route_info = map_service.calculate_trip_route(pickup_address, destination_address)
        if route_info:
            return {
                "distance_km": route_info["distance_km"],
                "duration_min": route_info["duration_min"],
                "pickup_coords": route_info["pickup_coords"],
                "destination_coords": route_info["destination_coords"],
                "has_real_data": True
            }
    except Exception as e:
        print(f"Error getting route info: {e}")
    
    # Fallback to estimates
    return {
        "distance_km": 5.0,
        "duration_min": 10.0,
        "pickup_coords": None,
        "destination_coords": None,
        "has_real_data": False
    }

# --- Get real trip requests from database ---
def create_trip_from_database(trip_id: int) -> Optional[Trip]:
    """Create a fully functional Trip object from database with Observer pattern integration"""
    try:
        # Get trip data from database
        row = db.get_trip_by_id(trip_id)
        if not row:
            print(f"Trip {trip_id} not found in database")
            return None
        
        # Extract trip data - trips table: id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id
        trip_db_id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id = row
        
        # Create Rider object from user_id with proper database lookup
        rider = create_rider_from_user_id(user_id) if user_id else Rider(user_id="guest", name="Guest", email="guest@example.com", phone="")
        
        # Create Trip object using trip_management.py with proper strategy normalization
        strategy_name = strategy.capitalize() if strategy else "Standard"
        trip = Trip(pickup, destination, rider, strategy_name)
        trip.trip_id = trip_db_id  # Use database ID
        
        # OBSERVER PATTERN INTEGRATION:
        # Attach the Rider as an observer to receive trip state notifications
        trip.attach(rider)
        print(f"[Observer Pattern] Attached rider {rider.name} as observer to trip {trip.trip_id}")
        
        # Create additional observer for comprehensive state change logging
        class TripStateLogger:
            def update(self, trip_obj, old_state, new_state):
                print(f"[Trip State] Trip {trip_obj.trip_id} state change: {old_state.value} → {new_state.value}")
        
        logger = TripStateLogger()
        trip.attach(logger)
        print(f"[Observer Pattern] Attached TripStateLogger to trip {trip.trip_id}")
        
        # Create driver if assigned and attach as observer
        if driver_id:
            driver = create_driver_from_user_id(driver_id)
            trip.driver = driver
            trip.attach(driver)  # Driver also observes trip state changes
            print(f"[Observer Pattern] Attached driver {driver.name} as observer to trip {trip.trip_id}")
        
        # Set current state from database using proper enum mapping
        state_mapping = {
            "requested": TripState.REQUESTED,
            "accepted": TripState.ACCEPTED,
            "in_progress": TripState.IN_PROGRESS,
            "completed": TripState.COMPLETED,
            "declined": TripState.DECLINED,
            "cancelled": TripState.CANCELLED
        }
        
        if state and state.lower() in state_mapping:
            trip._state = state_mapping[state.lower()]
            print(f"[Trip Management] Set trip {trip_id} state to {trip._state.value}")
        
        # Set route information with real map data if available
        try:
            route_info = map_service.calculate_trip_route(pickup, destination)
            if route_info:
                distance_km = route_info["distance_km"]
                duration_min = route_info["duration_min"]
            else:
                distance_km = float(distance) if distance else 5.0
                duration_min = 10.0  # Fallback duration
        except Exception as e:
            print(f"Error getting route info for trip {trip_id}: {e}")
            distance_km = float(distance) if distance else 5.0
            duration_min = 10.0
        
        # Use Trip object's set_route_info method for fare calculation
        trip.set_route_info(distance_km, duration_min)
        print(f"[Trip Management] Trip {trip_id} loaded with fare ${trip.base_fare:.2f} using {trip.fare_strategy.get_strategy_name()} strategy")
        
        return trip
        
    except Exception as e:
        print(f"Error creating Trip object from database for trip {trip_id}: {e}")
        return None

# Cache for trip requests (cache for 10 seconds for more real-time updates)
_trip_cache = {}
_trip_cache_time = 0
_TRIP_CACHE_TIMEOUT = 10  # seconds

def get_pending_trip_requests():
    """Get pending trip requests with lightweight processing and caching"""
    global _trip_cache, _trip_cache_time
    
    # Check cache first
    current_time = time.time()
    if current_time - _trip_cache_time < _TRIP_CACHE_TIMEOUT and _trip_cache:
        return _trip_cache.get('trips', [])
    
    try:
        pending_trips = db.get_pending_trips()
        trip_objects = []
        
        for row in pending_trips:
            try:
                # Use lightweight processing - only create full Trip object if needed
                trip_id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id = row
                
                # Get rider name efficiently without creating full Trip object
                rider_name = "Unknown Rider"
                if user_id:
                    try:
                        user_record = db.get_user_by_id(user_id)
                        if user_record:
                            rider_name = user_record[1]  # name field
                    except:
                        pass
                
                # Use cached route info or provide defaults to avoid API calls
                route_info = {
                    "distance_km": float(distance) if distance else 5.0,
                    "duration_min": (float(distance) * 2) if distance else 10.0,  # Rough estimate
                    "has_real_data": bool(distance)
                }
                
                # Create lightweight trip request without heavy Trip object creation
                trip_request = {
                    "id": trip_id,
                    "pickup": pickup,
                    "destination": destination,
                    "fare": float(fare) if fare else 10.0,
                    "eta": "Now",
                    "strategy": strategy or "Standard",
                    "created_at": created_at,
                    "distance_km": route_info["distance_km"],
                    "duration_min": route_info["duration_min"],
                    "has_real_data": route_info["has_real_data"],
                    "trip_object": None,  # Load Trip object only when accepting
                    "rider_name": rider_name,
                    "observer_count": 0  # Will be set when Trip object is created
                }
                trip_objects.append(trip_request)
                
            except Exception as e:
                print(f"Error processing trip request {row[0] if row else 'unknown'}: {e}")
                continue
        
        # Update cache
        _trip_cache = {'trips': trip_objects}
        _trip_cache_time = current_time
        
        return trip_objects
        
    except Exception as e:
        print(f"Error getting pending trips: {e}")
        return _trip_cache.get('trips', [])

def invalidate_caches():
    """Invalidate all caches when data changes"""
    global _driver_cache_time, _trip_cache_time
    _driver_cache_time = 0
    _trip_cache_time = 0

def get_mock_requests():
    """Keep original mock function for fallback"""
    return [
        {"id": "rq-101", "pickup": "350 5th Ave, New York, NY", "destination": "Times Square, New York, NY", "fare": 14.80, "eta": "Now"},
        {"id": "rq-102", "pickup": "1 Liberty Island, NY", "destination": "Brooklyn Bridge, NY", "fare": 22.10, "eta": "1 min"},
        {"id": "rq-103", "pickup": "JFK Terminal 4", "destination": "Midtown Manhattan", "fare": 45.30, "eta": "3 mins"}
    ]

def accept_trip_with_objects(trip_id: int, driver_id: int) -> bool:
    """Accept a trip using full Trip object functionality with Observer pattern integration"""
    try:
        # Import here to avoid circular dependency
        from fare_decorators import DriverRatingDecorator
        
        # Create Trip object from database with full Observer integration
        trip_obj = create_trip_from_database(trip_id)
        if not trip_obj:
            print(f"Failed to create Trip object for trip {trip_id}")
            return False
        
        # Create Driver object from database
        driver = create_driver_from_user_id(driver_id)
        if not driver:
            print(f"Failed to create Driver object for driver {driver_id}")
            return False
        
        # Get driver rating from database
        driver_record = db.get_user_by_id(driver_id)
        if driver_record:
            driver_rating = float(driver_record[2])  # rating at index 2
            
            # Apply driver rating decorator to fare strategy
            original_strategy = trip_obj.fare_strategy
            trip_obj.fare_strategy = DriverRatingDecorator(original_strategy, driver_rating)
            
            # Recalculate fare with rating decorator
            trip_obj.base_fare = trip_obj.fare_strategy.calculate_fare(
                trip_obj.distance_km,
                trip_obj.duration_min
            )
            print(f"[Decorator Pattern] Applied driver rating decorator (⭐{driver_rating}) - New fare: ${trip_obj.base_fare:.2f}")
        
        # OBSERVER PATTERN INTEGRATION:
        # Attach the Driver as an observer before accepting the trip
        trip_obj.attach(driver)
        print(f"[Observer Pattern] Attached driver {driver.name} as observer to trip {trip_id}")
        
        # Create additional observers for comprehensive monitoring
        class DriverActionLogger:
            def update(self, trip_obj, old_state, new_state):
                print(f"[Driver Action] Trip {trip_obj.trip_id} accepted by driver - State: {old_state.value} → {new_state.value}")
        
        driver_logger = DriverActionLogger()
        trip_obj.attach(driver_logger)
        
        # Accept the trip using Trip object's OOP method (will notify all observers)
        print(f"[Trip Management] Driver {driver.name} accepting trip {trip_id}")
        trip_obj.accept(driver)
        print(f"[Trip Management] Trip {trip_id} successfully accepted by {driver.name}, state: {trip_obj.state.value}")
        
        # Update database to reflect Trip object state WITH NEW DECORATED FARE
        db.update_trip_from_object(trip_id, trip_obj)
        db.assign_driver_to_trip(trip_id, driver_id)  # Update driver assignment in database
        
        print(f"[Observer Pattern] Trip {trip_id} acceptance complete with {len(trip_obj._observers)} observers notified")
        return True
        
    except Exception as e:
        print(f"Error accepting trip with Trip object: {e}")
        import traceback
        traceback.print_exc()
        return False
    
def start_trip_with_objects(trip_id: int) -> bool:
    """Start a trip using Trip object functionality with Observer notifications"""
    try:
        # Create Trip object from database with full integration
        trip_obj = create_trip_from_database(trip_id)
        if not trip_obj:
            return False
        
        # Start the trip using Trip object method (notifies all observers)
        old_state = trip_obj.state
        trip_obj.start()
        print(f"[Trip Management] Trip {trip_id} started: {old_state.value} → {trip_obj.state.value}")
        
        # Update database to reflect Trip object state
        db.update_trip_from_object(trip_id, trip_obj)
        
        return True
    except Exception as e:
        print(f"Error starting trip with Trip object: {e}")
        return False

def complete_trip_with_objects(trip_id: int) -> bool:
    """Complete a trip using Trip object functionality with Observer notifications"""
    try:
        # Create Trip object from database with full integration
        trip_obj = create_trip_from_database(trip_id)
        if not trip_obj:
            return False
        
        # Complete the trip using Trip object method (notifies all observers)
        old_state = trip_obj.state
        trip_obj.complete()
        print(f"[Trip Management] Trip {trip_id} completed: {old_state.value} → {trip_obj.state.value}")
        
        # Update database to reflect Trip object state
        db.update_trip_from_object(trip_id, trip_obj)
        
        return True
    except Exception as e:
        print(f"Error completing trip with Trip object: {e}")
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
    # Handle enum case variations
    "In_Progress": "In Progress",
    "IN_PROGRESS": "In Progress",
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
        <label for="driver_selection">Choose a driver to view their status:</label>
        <small style="color: #666; display: block; margin-bottom: 0.5rem;">
          📌 Available drivers can review new trip requests<br>
          🚗 Busy drivers will show their current trip progress
        </small>
        <select name="selected_driver_id" id="driver_selection" required>
          <option value="">-- Select a Driver --</option>
          {% for driver in drivers %}
            <option value="{{ driver.id }}" 
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

{% if selected_driver.is_available %}
<section class="card" style="margin-bottom: 2rem; background-color: #f8f9fa; border-left: 4px solid #007bff;">
  <h4 style="margin-top: 0; color: #007bff;">🎯 Trip Management Integration</h4>
  <div style="font-size: 0.9rem; color: #495057;">
    <p style="margin: 0.5rem 0;">This driver interface fully utilizes <strong>trip_management.py</strong> with comprehensive design pattern integration:</p>
    <ul style="margin: 0.5rem 0; padding-left: 1.5rem;">
      <li><strong>Observer Pattern:</strong> Automatic notifications when trip states change (riders, drivers, and loggers receive updates)</li>
      <li><strong>Strategy Pattern:</strong> Dynamic fare calculation using different algorithms (Standard, Surge, Premium)</li>
      <li><strong>Trip Object Lifecycle:</strong> Complete state management from request through completion</li>
      <li><strong>Database Integration:</strong> Trip objects sync with database for persistent state</li>
      <li><strong>Real-time Updates:</strong> All stakeholders notified instantly of trip status changes</li>
      <li><strong>Performance Optimized:</strong> Caching and lazy loading for faster page loads ⚡</li>
    </ul>
    <p style="margin: 0.5rem 0; padding: 0.5rem; background-color: #e8f4fd; border-radius: 4px;">
      💡 <strong>Observer Pattern in Action:</strong> When {{ selected_driver.name }} accepts/starts/completes trips, 
      all attached observers (rider, driver, state logger) automatically receive notifications.
    </p>
    <p style="margin: 0.5rem 0; padding: 0.5rem; background-color: #d4edda; border-radius: 4px; color: #155724;">
      ⚡ <strong>Performance:</strong> Driver data cached for 30s, trip data cached for 10s, route calculations cached for faster loading.
    </p>
  </div>
</section>
{% endif %}
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
        
        <div style="display: flex; gap: 1rem; margin: .5rem 0; font-size: .9rem; color: #666;">
          <span>📏 {{ "%.1f"|format(r.distance_km) }} km</span>
          <span>⏱️ {{ "%.0f"|format(r.duration_min) }} min</span>
          <span>🎯 {{ r.strategy }}</span>
          {% if r.has_real_data %}
            <span style="color: #28a745;">✅ Real route data</span>
          {% else %}
            <span style="color: #ffc107;">⚠️ Estimated</span>
          {% endif %}
        </div>
        
        {% if r.trip_object %}
        <div style="margin: .5rem 0; padding: .5rem; background-color: #e8f4fd; border-radius: 4px; border-left: 3px solid #007bff;">
          <p style="margin: 0; font-size: .85rem; color: #0056b3;">🎯 <strong>Trip Management Integration:</strong></p>
          <p style="margin: 0.25rem 0 0 0; font-size: .8rem; color: #666;">
            • Rider: {{ r.rider_name }}<br>
            • Observer Pattern: {{ r.observer_count }} observers attached<br>
            • Fare Strategy: {{ r.trip_object.fare_strategy.get_strategy_name() }}<br>
            • Trip ID: {{ r.trip_object.trip_id }}
          </p>
        </div>
        {% endif %}
        
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

    <p class="muted" style="margin-top:.5rem;">Trip ID: {{ trip.id }} · Fare: ${{ '%.2f'|format(trip.fare) }}</p>
    
    <!-- Driver and Rider Information -->
    <div style="margin-top:1rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
      <div style="padding: 0.75rem; background-color: #e8f4fd; border-radius: 6px; border-left: 4px solid #007bff;">
        <h4 style="margin: 0 0 0.5rem 0; color: #007bff;">🚗 Driver</h4>
        {% if driver_info %}
          <p style="margin: 0.25rem 0;"><strong>{{ driver_info.name }}</strong></p>
          <p style="margin: 0.25rem 0; font-size: 0.9rem;">Rating: ⭐ {{ driver_info.rating }}</p>
          <p style="margin: 0.25rem 0; font-size: 0.9rem;">{{ driver_info.vehicle_type }} - {{ driver_info.license_plate }}</p>
        {% else %}
          <p style="margin: 0; color: #6c757d;">Not assigned</p>
        {% endif %}
      </div>
      
      <div style="padding: 0.75rem; background-color: #fff3cd; border-radius: 6px; border-left: 4px solid #ffc107;">
        <h4 style="margin: 0 0 0.5rem 0; color: #856404;">👤 Rider</h4>
        {% if rider_info %}
          <p style="margin: 0.25rem 0;"><strong>{{ rider_info.name }}</strong></p>
          <p style="margin: 0.25rem 0; font-size: 0.9rem;">Rating: ⭐ {{ rider_info.rating }}</p>
        {% else %}
          <p style="margin: 0; color: #6c757d;">Unknown rider</p>
        {% endif %}
      </div>
    </div>
  </section>

  <section class="card" style="margin-top:1rem;">
    <h3 style="margin-top:0;">Driver Navigation</h3>
    <div class="map">{{ fmap|safe }}</div>
    <div style="margin-top:.5rem;">
      {% if trip.status == 'accepted' %}
        <p class="muted">
          🚗 <strong>Navigate to pickup location</strong><br>
          Real-time route shown with pickup (orange marker) and destination (red marker).<br>
          Blue car icon shows your simulated position heading to pickup.
        </p>
      {% elif trip.status == 'in_progress' %}
        <p class="muted">
          🚛 <strong>En route to destination</strong><br>
          Route visualization updated. Green route line indicates active trip.<br>
          Blue car icon shows your simulated position heading to destination.
        </p>
      {% elif trip.status == 'completed' %}
        <p class="muted">
          ✅ <strong>Trip completed</strong><br>
          Route shown in gray. Both locations marked with green completion icons.
        </p>
      {% else %}
        <p class="muted">
          📍 Interactive route map with pickup and destination markers.<br>
          Enhanced with real coordinate data and route visualization.
        </p>
      {% endif %}
    </div>
  </section>

  <form method="POST" action="{{ url_for('driver_home.trip_progress', trip_id=trip.id) }}" style="margin-top:1rem;">
    <div class="actions">
      {% if trip.status == 'accepted' %}
        <button type="submit" name="action" value="start" class="primary">
          🚗 Start Journey to Pickup
        </button>
      {% elif trip.status == 'in_progress' %}
        <button type="submit" name="action" value="complete" class="primary">
          ✅ Complete Trip (Arrived at Destination)
        </button>
      {% elif trip.status == 'completed' %}
        <a role="button" href="{{ url_for('driver_home.home') }}" class="secondary">
          ← Back to Driver Home
        </a>
      {% else %}
        <button type="submit" name="action" value="start"
                {% if trip.status not in ['accepted','requested'] %}disabled{% endif %}>
          Start Trip
        </button>
        <button type="submit" name="action" value="complete"
                {% if trip.status not in ['accepted','in_progress'] %}disabled{% endif %}>
          Complete Trip
        </button>
      {% endif %}
    </div>
    
    <div style="margin-top:.75rem; padding:.75rem; background-color: #f8f9fa; border-radius: 6px; border-left: 4px solid #007bff;">
      {% if trip.status == 'accepted' %}
        <strong>Next Step:</strong> Navigate to pickup location and start the trip
      {% elif trip.status == 'in_progress' %}
        <strong>Next Step:</strong> Navigate to destination and complete the trip
      {% elif trip.status == 'completed' %}
        <strong>Status:</strong> Trip completed successfully! 🎉
      {% else %}
        <strong>Current status:</strong> {{ status_label }}
      {% endif %}
    </div>
    
    <!-- Trip Management Integration Status -->
    <div style="margin-top: 1rem; padding: 0.75rem; background-color: #e8f4fd; border-radius: 6px; border-left: 4px solid #007bff;">
      <h4 style="margin: 0 0 0.5rem 0; color: #007bff; font-size: 1rem;">🎯 Trip Object Integration</h4>
      <div style="font-size: 0.85rem; color: #495057;">
        <p style="margin: 0.25rem 0;">✅ <strong>Observer Pattern:</strong> Trip state changes automatically notify all observers</p>
        <p style="margin: 0.25rem 0;">✅ <strong>Strategy Pattern:</strong> Dynamic fare calculation using {{ trip.strategy or 'Standard' }} strategy</p>
        <p style="margin: 0.25rem 0;">✅ <strong>State Management:</strong> Trip object manages state transitions ({{ status_label }})</p>
        <p style="margin: 0.25rem 0;">✅ <strong>Database Sync:</strong> Trip object state synchronized with persistent storage</p>
        <p style="margin: 0.25rem 0; padding: 0.5rem; background-color: #fff; border-radius: 3px; font-style: italic;">
          💡 This demonstrates complete trip_management.py utilization with Observer pattern, 
          Strategy pattern, and full object lifecycle management.
        </p>
      </div>
    </div>
  </form>
{% endif %}
"""

@driver_home.route("/", methods=["GET", "POST"])
def home():
    banner = None
    selected_driver = None
    
    # Only process form data on actual POST requests with form data
    if request.method == "POST" and request.form:
        action = request.form.get("action", "").strip()
        
        # Handle driver selection
        if action == "select_driver":
            selected_driver_id = request.form.get("selected_driver_id", "").strip()
            if selected_driver_id and selected_driver_id.isdigit():
                driver_record = db.get_user_by_id(int(selected_driver_id))
                if driver_record:
                    active_trip = db.get_active_trip_for_driver(driver_record[0])
                    is_available = active_trip is None
                    
                    # If driver is busy, redirect to their trip progress page
                    if not is_available and active_trip:
                        flash(f"Viewing active trip for driver: {driver_record[1]}")
                        return redirect(url_for('driver_home.trip_progress', trip_id=active_trip[0]))
                    
                    selected_driver = {
                        'id': driver_record[0],
                        'name': driver_record[1],
                        'rating': driver_record[2],
                        'role': driver_record[3],
                        'created_at': driver_record[4],
                        'vehicle_type': driver_record[5] if len(driver_record) > 5 else None,
                        'license_plate': driver_record[6] if len(driver_record) > 6 else None,
                        'is_available': is_available,
                        'status': 'Available' if is_available else 'Busy'
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
                    # Invalidate caches when data changes
                    invalidate_caches()
                    
                    # TRIP MANAGEMENT INTEGRATION:
                    # Use Trip object from trip_management.py for proper acceptance with Observer pattern
                    try:
                        success = accept_trip_with_objects(trip_id_int, driver_id_int)
                        if success:
                            driver_record = db.get_user_by_id(driver_id_int)
                            driver_name = driver_record[1] if driver_record else "Driver"
                            banner = {
                                "title": f"Request #{trip_id} accepted by {driver_name}! (Trip Management)",
                                "detail": "Trip accepted using Trip object with Observer pattern notifications to rider and driver.",
                            }
                            flash(f"Trip #{trip_id} successfully assigned to {driver_name} using Trip object with Observer notifications")
                        else:
                            banner = {
                                "title": f"Failed to accept request #{trip_id} (Trip Management)",
                                "detail": "Failed to create Trip object or assign driver. The trip may have been taken by another driver.",
                            }
                            flash("Failed to accept trip using Trip object - it may have been taken already!")
                    except Exception as e:
                        print(f"Error in Trip object acceptance: {e}")
                        # Fallback to direct database assignment
                        success = db.assign_driver_to_trip(trip_id_int, driver_id_int)
                        if success:
                            driver_record = db.get_user_by_id(driver_id_int)
                            driver_name = driver_record[1] if driver_record else "Driver"
                            banner = {
                                "title": f"Request #{trip_id} accepted by {driver_name}! (Fallback)",
                                "detail": "Trip assigned using fallback method due to Trip object error.",
                            }
                            flash(f"Trip #{trip_id} assigned to {driver_name} (fallback mode)")
                        else:
                            banner = {
                                "title": f"Failed to accept request #{trip_id}",
                                "detail": "The trip may have been taken by another driver.",
                            }
                            flash("Failed to assign trip - it may have been taken already!")
                else:  # decline
                    # Invalidate caches on data change
                    invalidate_caches()
                    
                    # TRIP MANAGEMENT INTEGRATION:
                    # Use Trip object for proper decline with Observer pattern notifications
                    try:
                        trip_obj = create_trip_from_database(trip_id_int)
                        if trip_obj:
                            # Use Trip object's decline method (will notify all observers)
                            old_state = trip_obj.state
                            trip_obj.decline()
                            print(f"[Trip Management] Trip {trip_id} declined using Trip object: {old_state.value} → {trip_obj.state.value}")
                            
                            # Update database to reflect Trip object state
                            db.update_trip_from_object(trip_id_int, trip_obj)
                            
                            banner = {
                                "title": f"Request #{trip_id} declined (Trip Management)",
                                "detail": "Trip declined using Trip object with Observer pattern notifications.",
                            }
                            flash(f"Trip #{trip_id} declined using Trip object with Observer notifications")
                        else:
                            # Fallback to direct database update if Trip object creation fails
                            print(f"Failed to create Trip object for decline, using fallback")
                            db.update_trip_status(trip_id_int, "declined")
                            banner = {
                                "title": f"Request #{trip_id} declined.",
                                "detail": "Trip request has been declined.",
                            }
                            flash(f"Trip #{trip_id} declined")
                    except Exception as e:
                        print(f"Error declining trip with Trip object: {e}")
                        # Fallback to direct database update
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
        driver_info = None
        rider_info = None
    else:
        # TRIP MANAGEMENT INTEGRATION:
        # Create Trip object using enhanced create_trip_from_database with full Observer pattern
        trip_obj = create_trip_from_database(trip_id)
        if not trip_obj:
            print(f"Failed to create Trip object from database for trip {trip_id}")
            # Fallback to manual Trip creation
            rider = create_rider_from_trip_data(row)
            trip_obj = Trip(row[2], row[3], rider, row[4])  # pickup, destination, strategy
            trip_obj.trip_id = trip_id
        
        # Get current state from Trip object (more reliable than database)
        current_state = trip_obj.state.value if trip_obj else (row[6] if len(row) > 6 else "requested")
        print(f"[Trip Management] Trip {trip_id} loaded with state: {current_state}, observers: {len(trip_obj._observers) if trip_obj else 0}")
        
        # Get driver and rider information
        driver_id = row[9] if len(row) > 9 else None  # driver_id from trips table
        rider_id = row[8] if len(row) > 8 else None   # user_id from trips table
        
        driver_info = None
        rider_info = None
        
        if driver_id:
            driver_record = db.get_user_by_id(driver_id)
            if driver_record:
                driver_info = {
                    'id': driver_record[0],
                    'name': driver_record[1],
                    'rating': driver_record[2],
                    'vehicle_type': driver_record[5] if len(driver_record) > 5 else 'Unknown',
                    'license_plate': driver_record[6] if len(driver_record) > 6 else 'N/A'
                }
        
        if rider_id:
            rider_record = db.get_user_by_id(rider_id)
            if rider_record:
                rider_info = {
                    'id': rider_record[0],
                    'name': rider_record[1],
                    'rating': rider_record[2]
                }
        
        trip = {
            "id": row[0],
            "pickup": row[2],
            "destination": row[3], 
            "strategy": row[4],
            "fare": row[5],
            "status": current_state,
        }
        
        # Handle state transitions using enhanced Trip object methods with Observer notifications
        if request.method == "POST":
            action = (request.form.get("action") or "").strip()
            
            if action == "start" and current_state in ["accepted", "requested"]:
                # TRIP MANAGEMENT INTEGRATION:
                # Start the trip using Trip object with Observer pattern notifications
                try:
                    success = start_trip_with_objects(trip_id)
                    if success:
                        # Refresh trip object to get updated state
                        updated_trip_obj = create_trip_from_database(trip_id)
                        if updated_trip_obj:
                            trip["status"] = updated_trip_obj.state.value
                            print(f"[Trip Management] Trip {trip_id} started successfully with Observer notifications")
                        else:
                            print(f"Warning: Could not refresh Trip object after starting trip {trip_id}")
                    else:
                        print(f"Failed to start trip {trip_id} using Trip object")
                except Exception as e:
                    print(f"Error starting trip with Trip object: {e}")
                    # Fallback to direct Trip object method
                    trip_obj.start()
                    db.update_trip_from_object(trip_id, trip_obj)
                    trip["status"] = trip_obj.state.value
                
            elif action == "complete" and current_state in ["accepted", "in_progress"]:
                # TRIP MANAGEMENT INTEGRATION:
                # Complete the trip using Trip object with Observer pattern notifications
                try:
                    success = complete_trip_with_objects(trip_id)
                    if success:
                        # Refresh trip object to get updated state
                        updated_trip_obj = create_trip_from_database(trip_id)
                        if updated_trip_obj:
                            trip["status"] = updated_trip_obj.state.value
                            print(f"[Trip Management] Trip {trip_id} completed successfully with Observer notifications")
                        else:
                            print(f"Warning: Could not refresh Trip object after completing trip {trip_id}")
                    else:
                        print(f"Failed to complete trip {trip_id} using Trip object")
                except Exception as e:
                    print(f"Error completing trip with Trip object: {e}")
                    # Fallback to direct Trip object method
                    trip_obj.complete()
                    db.update_trip_from_object(trip_id, trip_obj)
                    trip["status"] = trip_obj.state.value

        status_label = TRIP_STATUS_LABELS.get(trip["status"], trip["status"].title())
    
    # Create enhanced driver map with trip route and status
    if trip:
        fmap_html = make_driver_map(
            trip_pickup=trip["pickup"],
            trip_destination=trip["destination"],
            trip_status=trip["status"]
        )
    else:
        fmap_html = make_driver_map()

    body = render_template_string(
        TRIP_PROGRESS_BODY,
        trip=trip,
        status_label=status_label,
        fmap=fmap_html,
        driver_info=driver_info,
        rider_info=rider_info,
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

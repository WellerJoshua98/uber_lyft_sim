"""
Simple demonstration of core OOP patterns working together.
"""
from user_classes import Rider, Driver
from trip_management import Trip
from fare_calc import FareStrategyFactory
from map_integration import MockMapService

print("=" * 60)
print("UBER/LYFT SIMULATION - CORE OOP DEMO")
print("=" * 60)

# 1. Create users
print("\n1. Creating users...")
rider = Rider("R001", "Alice Smith", "alice@email.com", "555-0101")
driver = Driver("D001", "Bob Johnson", "bob@email.com", "555-0201", 
               "Toyota Camry", "ABC-123")
print(f"   ✓ {rider}")
print(f"   ✓ {driver}")

# 2. Create trip with Strategy pattern (via Factory)
print("\n2. Creating trip with Surge pricing...")
trip = rider.request_trip(
    pickup="350 5th Ave, New York, NY",
    destination="Times Square, New York, NY",
    strategy_name="Surge"
)
print(f"   ✓ {trip}")

# 3. Calculate route using Map service
print("\n3. Calculating route with map service...")
map_service = MockMapService()
route = map_service.calculate_trip_route(trip.pickup, trip.destination)
if route:
    trip.set_route_info(route['distance_km'], route['duration_min'])
    print(f"   ✓ Distance: {trip.distance_km:.2f} km")
    print(f"   ✓ Duration: {trip.duration_min:.1f} min")
    print(f"   ✓ Fare (Surge): ${trip.base_fare:.2f}")

# 4. Observer pattern - Driver accepts trip
print("\n4. Driver accepting trip (Observer pattern)...")
driver.accept_trip(trip)  # Both rider and driver get notified!

# 5. Complete the trip
print("\n5. Starting and completing trip...")
trip.start()
driver.complete_trip()

# 6. Show results
print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
print(f"Trip state: {trip.state.value}")
print(f"Rider trip history: {rider.trip_history}")
print(f"Driver trip history: {driver.trip_history}")
print(f"Driver available: {driver.is_available}")

# 7. Compare different strategies
print("\n" + "=" * 60)
print("STRATEGY PATTERN COMPARISON")
print("=" * 60)
print(f"Route: {trip.distance_km:.1f} km, {trip.duration_min:.1f} min\n")

for strategy_name in FareStrategyFactory.get_available_strategies():
    strategy = FareStrategyFactory.create_strategy(strategy_name)
    fare = strategy.calculate_fare(trip.distance_km, trip.duration_min)
    print(f"  {strategy_name:12s}: ${fare:6.2f}")

print("\n" + "=" * 60)
print("✓ All patterns working correctly!")
print("=" * 60)
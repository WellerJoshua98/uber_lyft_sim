# Uber/Lyft Simulation System

A ride-sharing simulation demonstrating OOP design patterns, real-time trip management, and data analytics. Built with Python, Flask, and SQLite.

## Overview

This project simulates a complete ride-sharing platform with:
- Trip lifecycle management (request → accept → in progress → complete)
- Multiple pricing strategies (Standard, Surge, Premium)
- Dynamic fare modifiers (tips, discounts, promos)
- Web interface for riders and drivers
- Real-time map integration with OpenRouteService API
- Analytics dashboard with visualizations

**Design Patterns Implemented:**
- **Observer Pattern** (trip state notifications)
- **Strategy Pattern** (fare calculation algorithms)
- **Factory Pattern** (strategy creation)
- **Decorator Pattern** (dynamic fare modifications)

## Quick Start
```bash
# 1. Setup environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Add API key for real maps
echo ORS_API_KEY=your_api_key_here > .env

# 4. Run the application
python app.py  # Web interface at http://localhost:5000
python demo.py  # Command-line demo with all patterns
```

## Features

### Web Interface
- **Rider Portal** (`/`): Request trips, view history, rate drivers
- **Driver Portal** (`/driver`): Accept trips, navigate routes, complete rides
- Interactive maps showing pickup/destination with route visualization
- Real-time fare calculations using different pricing strategies

### Analytics Dashboard
Run `python trip_manager_dashboard.py` or open the Jupyter notebook to generate:
- KPI summary (trips, revenue, averages)
- Daily trip volume charts
- Revenue by strategy analysis
- Interactive trip map

### Programmatic API
```python
from trip_manager_dashboard import TripController
from fare_calc import FareStrategyFactory
from fare_decorators import TipDecorator, DiscountDecorator

ctl = TripController()
ctl.new_rider(name="Alice", rating="4.9")
ctl.new_driver(name="Bob", vehicle_type="Tesla Model 3")

# Create trip with Premium pricing
team_id, db_id = ctl.create_trip(
    pickup="34.101,-118.326",
    destination="33.941,-118.408",
    rider_name="Alice",
    strategy="Premium"
)

# Apply decorators for dynamic fare modification
base_strategy = FareStrategyFactory.create_strategy("Standard")
with_tip = TipDecorator(base_strategy, tip_percentage=20)
fare = with_tip.calculate_fare(distance_km=10, duration_min=15)
```

## Project Structure
```
uber_lyft_sim/
├── app.py                    # Flask application
├── db.py                     # Database layer (SQLite)
├── trip_management.py        # Trip class with Observer pattern
├── user_classes.py           # Rider/Driver classes
├── fare_calc.py              # Strategy pattern for pricing
├── fare_decorators.py        # Decorator pattern for fare modifiers
├── map_integration.py        # OpenRouteService integration
├── demo.py                   # Demonstrates all design patterns
├── sim_ui/
│   ├── rider_home.py         # Rider web interface
│   └── driver_home.py        # Driver web interface
└── trip_manager_dashboard.*  # Analytics dashboard
```

## Database Schema

**trips**: id, created_at, pickup, destination, strategy, fare, state, distance, user_id, driver_id

**users**: id, name, rating, role (rider/driver), vehicle_type, license_plate

**trip_reviews**: id, trip_id, rating, created_at

## Design Patterns

### Observer Pattern
Trip state changes automatically notify all observers (riders, drivers):
```python
trip.attach(rider)
trip.attach(driver)
trip.accept(driver)  # Both receive notification
# [Rider Alice] Trip 1001 changed: requested → accepted
# [Driver Bob] Trip 1001 changed: requested → accepted
```

### Strategy Pattern
Interchangeable fare calculation algorithms:
- **Standard**: Base rates ($2.50 + $1.50/km + $0.30/min)
- **Surge**: 1.3x multiplier during high demand
- **Premium**: Luxury service with higher rates
```python
strategy = FareStrategyFactory.create_strategy("Surge")
fare = strategy.calculate_fare(distance_km=10, duration_min=15)
```

### Factory Pattern
Centralized creation of fare strategies:
```python
for strategy_name in FareStrategyFactory.get_available_strategies():
    strategy = FareStrategyFactory.create_strategy(strategy_name)
    fare = strategy.calculate_fare(distance, duration)
```

### Decorator Pattern
Dynamically add fare modifications without changing base strategies. **Includes automatic rating-based adjustments:**
```python
# Ratings automatically applied in UI
# High-rated drivers: +5% premium
# High-rated riders: -3% loyalty discount

# Manual example:
from fare_decorators import DriverRatingDecorator, RiderRatingDecorator

base = FareStrategyFactory.create_strategy("Standard")
with_ratings = DriverRatingDecorator(
    RiderRatingDecorator(base, rider_rating=5.0),
    driver_rating=4.9
)
fare = with_ratings.calculate_fare(10, 15)
```

**Rating System Integration:**
- **Driver Ratings**: 
  - ⭐ 4.9-5.0: +5% premium (high demand for excellent drivers)
  - ⭐ 4.5-4.8: No adjustment
  - ⭐ Below 4.5: -5% discount
- **Rider Ratings**:
  - ⭐ 5.0: -3% loyalty discount
  - ⭐ 4.8-4.9: -2% loyalty discount
  - ⭐ Below 4.8: No discount

Ratings are automatically applied when:
- Riders preview fares (rider rating decorator applied)
- Drivers accept trips (driver rating decorator applied)

### Map Integration
- Real routing via OpenRouteService API (with API key)
- Mock service with simulated data (fallback without API key)
- Geocoding and distance/duration calculations

## Configuration

Create `.env` file for real map data:
```bash
ORS_API_KEY=your_api_key_here
```

Without an API key, the system uses MockMapService automatically.

## Usage Examples

### Web Interface
1. Start app: `python app.py`
2. http://127.0.0.1:5000

### Command Line Demo
```bash
python demo.py  # Demonstrates 3 design patterns (No Decorator implemented in demo yet)
```

Output includes:
- User creation
- Trip lifecycle with Observer notifications
- Strategy pattern fare comparisons


### Analytics Dashboard
```bash
python trip_manager_dashboard.py  # Generates charts and map
jupyter notebook trip_manager_dashboard.ipynb  # Interactive analysis
```

## Dependencies

- flask==3.0.0
- folium==0.15.1
- requests==2.31.0
- python-dotenv==1.0.0
- pandas (for dashboard)
- matplotlib (for dashboard)

## Notes

- Database (`app.db`) is auto-created on first run
- Reset database: `rm app.db` and restart app
- Mock map service provides realistic simulated data when API key is unavailable
- All four design patterns are fully integrated and functional
- Decorators can be stacked in any order for complex fare calculations

## Development

To extend functionality:
1. **Add fare strategies**: Create new classes in `fare_calc.py`, register in Factory
2. **Add decorators**: Create new decorator classes in `fare_decorators.py`
3. **Add observers**: Implement Observer interface in `user_classes.py`
4. **Add routes**: Create new Flask blueprints in `sim_ui/`


Built for educational purposes. Demonstrates real-world application of software design patterns.
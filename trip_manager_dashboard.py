#!/usr/bin/env python
# coding: utf-8

"""
Trip Manager + Stats Dashboard for Uber/Lyft Simulation.

- TripController coordinates Trip creation, riders/drivers, map routing, and DB persistence.
- Uses Strategy pattern (fare strategies), Observer pattern (Trip/Rider/Driver).
- Dashboard generates KPIs, plots (trips/day, trips by strategy, revenue/day),
  and an interactive Folium map.
"""

import os
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Tuple, Dict

import pandas as pd
import matplotlib.pyplot as plt
import folium

import db
from trip_management import Trip
from user_classes import Rider, Driver, TripState
from map_integration import MapService, MockMapService

# Map service selection (live ORS vs Mock)

if os.getenv("ORS_API_KEY"):
    map_service = MapService()
    print("MapService: OpenRouteService (live)")
else:
    map_service = MockMapService()
    print("MapService: MOCK")


# DB init + Trip state mapping

db.init_db()
print("DB path:", Path(db.DB_PATH).resolve())

TRIPSTATE_TO_DB = {
    TripState.REQUESTED: "requested",
    TripState.ACCEPTED: "accept",
    TripState.DECLINED: "declined",
    TripState.IN_PROGRESS: "in progress",
    TripState.COMPLETED: "completed",
    TripState.CANCELLED: "cancelled",
}


# Routing helpers


def _parse_latlng(s: str) -> Optional[Tuple[float, float]]:
    if not isinstance(s, str) or "," not in s:
        return None
    try:
        a, b = s.split(",", 1)
        return float(a.strip()), float(b.strip())
    except Exception:
        return None

def get_route_info(pickup: str, destination: str) -> Dict[str, float]:
    """
    Returns {'distance_km': float, 'duration_min': float}

    Uses:
      - direct coords if pickup/destination are 'lat,lng'
      - or geocode + route via MapService / MockMapService
    """
    p = _parse_latlng(pickup)
    d = _parse_latlng(destination)

    if p and d:
        data = map_service.get_route(p, d)
        if not data:
            raise RuntimeError("Routing failed for provided coordinates.")
        return {
            "distance_km": float(data["distance_km"]),
            "duration_min": float(data["duration_min"])
        }

    data = map_service.calculate_trip_route(pickup, destination)
    if not data:
        raise RuntimeError("Routing failed (geocode + route).")
    return {
        "distance_km": float(data["distance_km"]),
        "duration_min": float(data["duration_min"])
    }


# TripController


@contextmanager
def _conn():
    with db.connect() as con:
        yield con

def _slug(s: str) -> str:
    return "".join(
        ch for ch in s.lower().strip().replace(" ", "_")
        if ch.isalnum() or ch in "._-"
    )

class TripController:
    """
    Manages:
    - Riders/Drivers (from user_classes)
    - Trip objects (from trip_management)
    - Lifecycle updates (accept, start, complete, cancel)
    - Persists data to SQLite using db.py
    """
    def __init__(self):
        self.live_trips = {}   # team_trip_id -> (Trip, db_id)
        self.riders = {}       # name -> Rider
        self.drivers = {}      # name -> Driver

    def _get_or_create_user(self, name: str, role: str, rating: str):
        """Create a DB user only if they don't already exist."""
        rows = db.get_all_users(limit=9999)
        for r in rows:
            if r[1] == name and r[3] == role:
                return r[0]
        return db.create_user(name, rating, role)

    def new_rider(self, name="Rider A", email=None, phone=None, rating="4.9"):
        """Create a Rider(user_id, name, email, phone)."""
        self._get_or_create_user(name, role="rider", rating=rating)

        uid = f"rider_{_slug(name)}"
        email = email or f"{_slug(name)}@example.com"
        phone = phone or "000-000-0000"

        rider = Rider(uid, name, email, phone)
        self.riders[name] = rider
        return name

    def new_driver(self, name="Driver 1", email=None, phone=None,
                   vehicle_type="Sedan", license_plate="TEST123", rating="4.8"):
        """Create a Driver(user_id, name, email, phone, vehicle_type, license_plate)."""
        self._get_or_create_user(name, role="driver", rating=rating)

        uid = f"driver_{_slug(name)}"
        email = email or f"{_slug(name)}@example.com"
        phone = phone or "000-000-0000"

        driver = Driver(uid, name, email, phone, vehicle_type, license_plate)
        self.drivers[name] = driver
        return name

    def accept(self, team_trip_id: int, driver_name="Driver 1"):
        """Driver accepts a trip + persist new state."""
        trip, db_id = self.live_trips[team_trip_id]

        drv = self.drivers.get(driver_name)
        if drv is None:
            uid = f"driver_{_slug(driver_name)}"
            drv = Driver(
                uid,
                driver_name,
                f"{_slug(driver_name)}@example.com",
                "000-000-0000",
                "Sedan",
                "TEST123",
            )
            self._get_or_create_user(driver_name, role="driver", rating="4.8")
            self.drivers[driver_name] = drv

        trip.accept(drv)
        db.update_trip_status(db_id, TRIPSTATE_TO_DB[trip.state])

    def start(self, team_trip_id: int):
        trip, db_id = self.live_trips[team_trip_id]
        trip.start()
        db.update_trip_status(db_id, TRIPSTATE_TO_DB[trip.state])

    def complete(self, team_trip_id: int):
        trip, db_id = self.live_trips[team_trip_id]
        trip.complete()
        db.update_trip_status(db_id, TRIPSTATE_TO_DB[trip.state])

    def decline(self, team_trip_id: int):
        trip, db_id = self.live_trips[team_trip_id]
        trip.decline()
        db.update_trip_status(db_id, TRIPSTATE_TO_DB[trip.state])

    def cancel(self, team_trip_id: int):
        """Cancel trip in DB (Trip class may not implement cancel())."""
        _trip, db_id = self.live_trips[team_trip_id]
        db.update_trip_status(db_id, "cancelled")
      
    def trips_df(self, limit=1000) -> pd.DataFrame:
        """Return trips as a DataFrame for analytics."""
        rows = db.list_trips(limit=limit)

        # Your trips table now has 10 columns, so give Pandas 10 names
        df = pd.DataFrame(
          rows,
          columns=[
            "id",
            "created_at",
            "pickup",
            "destination",
            "strategy",
            "fare",
            "state",
            "distance",
            "rider_id",
            "driver_id",
          ],
    )

    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])

    return df


    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])

    return df




    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])

    return df




    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])

    return df

        if not df.empty:
            df["created_at"] = pd.to_datetime(df["created_at"])
        return df


# Override create_trip to satisfy NOT NULL distance


def _tripcontroller_create_trip(self, pickup: str, destination: str,
                                rider_name="Rider A", strategy="Standard") -> tuple[int, int]:
    """
    Replacement for TripController.create_trip that:
    - Creates in-memory Trip (using Strategy pattern for fare).
    - Computes route via map service.
    - Inserts into DB including distance (NOT NULL constraint).
    """
    # 1) Ensure rider exists
    rider = self.riders.get(rider_name)
    if rider is None:
        uid = f"rider_{_slug(rider_name)}"
        rider = Rider(uid, rider_name, f"{_slug(rider_name)}@example.com", "000-000-0000")
        self._get_or_create_user(rider_name, role="rider", rating="5.0")
        self.riders[rider_name] = rider

    # 2) Create in-memory Trip
    trip = Trip(
        pickup=pickup,
        destination=destination,
        rider=rider,
        strategy_name=strategy,
    )

    # 3) Route + fare
    route = get_route_info(pickup, destination)
    trip.set_route_info(
        distance_km=route["distance_km"],
        duration_min=route["duration_min"],
    )
    distance_int_km = max(1, int(round(route["distance_km"])))

    # 4) Insert directly into DB with distance
    with _conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO trips (pickup, destination, strategy, fare, state, distance)
            VALUES (?, ?, ?, ?, 'requested', ?)
            """,
            (pickup, destination, strategy.lower(), float(trip.base_fare), distance_int_km),
        )
        db_trip_id = cur.lastrowid

    # 5) Save mapping
    self.live_trips[trip.trip_id] = (trip, db_trip_id)
    return trip.trip_id, db_trip_id

# Apply override
TripController.create_trip = _tripcontroller_create_trip


# KPIs + Plots + Map


def kpis(df: pd.DataFrame) -> dict:
    """Compute summary KPIs from trips DataFrame."""
    if df.empty:
        return {
            "trips": 0,
            "completed": 0,
            "avg_fare": 0.0,
            "total_revenue": 0.0,
            "avg_distance_km": 0.0,
        }
    return {
        "trips": int(len(df)),
        "completed": int((df["state"] == "completed").sum()),
        "avg_fare": round(df["fare"].mean(), 2),
        "total_revenue": round(df.loc[df["state"] == "completed", "fare"].sum(), 2),
        "avg_distance_km": round(df["distance"].mean(), 2),
    }

def build_trip_map(df: pd.DataFrame,
                   html_path: str = "dashboard_map.html",
                   center=(34.0522, -118.2437),
                   zoom_start=11) -> str:
    """Create a Folium map of trips and save to HTML."""
    m = folium.Map(location=center, zoom_start=zoom_start)

    if df.empty:
        m.save(html_path)
        return html_path

    def parse_latlng(s):
        if not isinstance(s, str) or "," not in s:
            return None
        try:
            a, b = s.split(",", 1)
            return float(a.strip()), float(b.strip())
        except Exception:
            return None

    for _, r in df.iterrows():
        p = parse_latlng(r["pickup"])
        d = parse_latlng(r["destination"])
        if not (p and d):
            continue
        folium.PolyLine([p, d],
                        tooltip=f"Trip {r['id']} ({r['strategy']})").add_to(m)
        folium.CircleMarker(p, radius=4, popup=f"Pickup {r['id']}").add_to(m)
        folium.CircleMarker(d, radius=4, popup=f"Dropoff {r['id']}").add_to(m)

    m.save(html_path)
    return html_path


# Demo run 


if __name__ == "__main__":
    import datetime as dt

    # 0) Clear old trips so we don't double-count
    with db.connect() as con:
        con.execute("DELETE FROM trips")

    # 1) New controller, rider, and driver
    ctl = TripController()
    ctl.new_rider(
        name="Rider A",
        email="rider.a@example.com",
        phone="555-000-0001",
        rating="4.9",
    )
    ctl.new_driver(
        name="Driver 1",
        email="driver.1@example.com",
        phone="555-000-0002",
        vehicle_type="Sedan",
        license_plate="7ABC123",
        rating="4.8",
    )

    # 2) Synthetic scenarios
    trip_scenarios = [
        {"offset": 4, "strategy": "Standard", "final_state": "completed"},
        {"offset": 4, "strategy": "Premium",  "final_state": "completed"},
        {"offset": 3, "strategy": "Surge",    "final_state": "completed"},
        {"offset": 3, "strategy": "Standard", "final_state": "cancelled"},
        {"offset": 2, "strategy": "Premium",  "final_state": "completed"},
        {"offset": 2, "strategy": "Standard", "final_state": "requested"},
        {"offset": 1, "strategy": "Surge",    "final_state": "completed"},
        {"offset": 1, "strategy": "Standard", "final_state": "completed"},
        {"offset": 0, "strategy": "Premium",  "final_state": "completed"},
        {"offset": 0, "strategy": "Surge",    "final_state": "cancelled"},
    ]

    today = dt.date.today()
    created_trip_ids = []

    for scenario in trip_scenarios:
        offset = scenario["offset"]
        strategy = scenario["strategy"]
        final_state = scenario["final_state"]

        team_id, db_id = ctl.create_trip(
            pickup="34.101,-118.326",          # Hollywood coords
            destination="33.941,-118.408",     # LAX coords
            rider_name="Rider A",
            strategy=strategy,
        )

        if final_state in ("completed", "cancelled", "requested"):
            if final_state != "requested":
                ctl.accept(team_id, driver_name="Driver 1")

            if final_state == "completed":
                ctl.start(team_id)
                ctl.complete(team_id)
            elif final_state == "cancelled":
                ctl.cancel(team_id)

        trip_date = today - dt.timedelta(days=offset)
        created_at_str = f"{trip_date} 10:00:00"

        with db.connect() as con:
            con.execute(
                "UPDATE trips SET created_at = ? WHERE id = ?",
                (created_at_str, db_id),
            )

        created_trip_ids.append(db_id)

    print("Created DB trip IDs:", created_trip_ids)

    df = ctl.trips_df()
    if not df.empty:
        df["date"] = df["created_at"].dt.date
        df["fare"] = pd.to_numeric(df["fare"], errors="coerce").fillna(0.0)
        df["distance"] = (
            pd.to_numeric(df["distance"], errors="coerce").fillna(0).astype(int)
        )

    print("KPI:", kpis(df))

    # Trips per day
    plt.figure()
    plt.title("Trips per Day")
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center", va="center")
    else:
        grouped = df.groupby("date").size()
        plt.bar(grouped.index.astype(str), grouped.values)
        plt.xlabel("Date")
        plt.ylabel("Trips")
        plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig("static/trips_per_day.png")
    plt.show()

    # Trips by fare type
    plt.figure()
    plt.title("Trips by Fare Type")
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center", va="center")
    else:
        counts = df["strategy"].str.title().value_counts()
        plt.bar(counts.index.astype(str), counts.values)
        plt.xlabel("Fare Type")
        plt.ylabel("Trips")
    plt.tight_layout()
    plt.savefig("static/trips_by_strategy.png")
    plt.show()

    # Revenue by day
    plt.figure()
    plt.title("Revenue by Day (Completed)")
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center", va="center")
    else:
        rev = df[df["state"] == "completed"].groupby("date")["fare"].sum()
        plt.bar(rev.index.astype(str), rev.values)
        plt.xlabel("Date")
        plt.ylabel("Revenue ($)")
        plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig("static/revenue_by_day.png")
    plt.show()

    # Map
    build_trip_map(df, "dashboard_map.html")
    print("Saved map → dashboard_map.html")

## Coded with help from chat gpt
import os
import sqlite3
from contextlib import contextmanager

# Path for database
DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")

# Queries to create necessary tables in our system
SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS trips(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    pickup TEXT NOT NULL,
    destination TEXT NOT NULL,
    strategy TEXT NOT NULL,
    fare REAL NOT NULL,
    state TEXT NOT NULL DEFAULT 'requested', -- requested | accept | declined | completed | cancelled
    distance INTEGER NOT NULL,
    user_id INTEGER,
    driver_id INTEGER
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rating Text NOT NULL,
    role TEXT CHECK(role IN ('rider','driver')) DEFAULT 'rider',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trip_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(trip_id) REFERENCES trips(id) ON DELETE CASCADE
);
"""


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with connect() as con:
        con.executescript(SCHEMA)

#Trip Helpers
def create_trip(pickup: str, destination: str, strategy: str, fare: float, user_id: int = None) -> int:
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO trips (pickup, destination, strategy, fare, state, distance, user_id) VALUES (?, ?, ?, ?, 'requested', 5, ?)",
            (pickup, destination, strategy, fare, user_id)
        )
        trip_id = cur.lastrowid
        if trip_id is None:
            raise RuntimeError("Failed to create trip")
        return trip_id

def get_trip_by_id(trip_id: int):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM trips WHERE id = ?",
            (trip_id,)
        )
        return cur.fetchone()

def list_trips(limit=50):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM trips ORDER BY datetime(created_at) DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()


def get_pending_trips():
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM trips WHERE state = 'requested' ORDER BY datetime(created_at) ASC"
        )
        return cur.fetchall()

def update_trip_status(trip_id: int, new_status:str):
    with connect() as con:
        con.execute("UPDATE trips SET state = ? WHERE id = ?", (new_status, trip_id))  


def get_driver_for_trip(trip_id: int):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM users "
            "JOIN trips ON users.id = trips.driver_id "
            "WHERE trips.id = ? AND users.role = 'driver'",
            (trip_id,)
        )
        return cur.fetchone()

# --- Users Helper ---
def create_user(name: str, rating: str, role: str) -> int:
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO users (name, rating, role) VALUES (?, ?, ?)",
            (name, rating, role)
        )
        user_id = cur.lastrowid
        if user_id is None:
            raise RuntimeError("Failed to create user")
        return user_id

def get_user_by_id(user_id: int):
    """Get a user by their ID from the database"""
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT id, name, rating, role, created_at FROM users WHERE id = ?",
            (user_id,)
        )
        return cur.fetchone()

def get_all_users(limit: int = 50):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM users ORDER BY datetime(created_at) DESC LIMIT ?",
            (limit,)
        )  
        return cur.fetchall()

def update_user_rating(user_id: int, new_rating: str):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "UPDATE users SET rating = ? WHERE id = ?",
            (new_rating, user_id)
        )



# --- Trip Reviews Helper ---
def get_review_by_trip_id(trip_id: int):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM trip_reviews WHERE trip_id = ?",
            (trip_id,)
        )
        return cur.fetchone()
    
def create_update_review(trip_id: int, rating: int):
    with connect() as con:
        cur = con.cursor()
        existing_review = get_review_by_trip_id(trip_id)
        if existing_review:
            cur.execute(
                "UPDATE trip_reviews SET rating = ? WHERE trip_id = ?",
                (rating, trip_id)
            )
        else:
            cur.execute(
                "INSERT INTO trip_reviews (trip_id, rating) VALUES (?, ?)",
                (trip_id, rating)
            )

# Trip Management Integration Helpers
def create_trip_from_object(trip_obj) -> int:
    """Create a database trip record from a Trip object"""
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO trips (pickup, destination, strategy, fare, state, distance) VALUES (?, ?, ?, ?, ?, ?)",
            (trip_obj.pickup, trip_obj.destination, trip_obj.fare_strategy.get_strategy_name(), 
             trip_obj.base_fare, trip_obj.state.value, int(trip_obj.distance_km))
        )
        trip_id = cur.lastrowid
        if trip_id is None:
            raise RuntimeError("Failed to create trip")
        return trip_id

def update_trip_from_object(trip_id: int, trip_obj):
    """Update database trip record from Trip object"""
    with connect() as con:
        con.execute(
            "UPDATE trips SET state = ?, fare = ?, distance = ? WHERE id = ?",
            (trip_obj.state.value, trip_obj.base_fare, int(trip_obj.distance_km), trip_id)
        )

def get_trip_state(trip_id: int) -> str:
    """Get the current state of a trip"""
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT state FROM trips WHERE id = ?", (trip_id,))
        result = cur.fetchone()
        return result[0] if result else "unknown"
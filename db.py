import os
import sqlite3
from contextlib import contextmanager

# Path for database
DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")

# Queries to create necessary tables in our system
SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS trips(
    id INTEGER PRIMARY KEY,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
    pickup TEXT NOT NULL,
    destination TEXT NOT NULL,
    strategy TEXT NOT NULL
    fare REAL NOT NULL,
    state TEXT NOT NULL DEFAULT 'requested' -- requested | accept | declined | completed | cancelled
    distance INTEGER NOT NULL
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
def create_trip(pickup: str, destination:str, strategy: str, fare: float) -> int:
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO trips (pickup, destination, strategy, fare, state) VALUES (?, ?, ?, ?, 'requested)",
            (pickup, destination, strategy, fare)
        )
        return cur.lastrowid


def list_trips(limit=100):
    with connect() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM trips ORDER BY datetime(created_at) DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()
    
def update_trip_status(trip_id: int, new_status:str):
    with connect() as con:
        con.execute("UPDATE trips SET state = ? WHERE id = ?", (new_status, trip_id))
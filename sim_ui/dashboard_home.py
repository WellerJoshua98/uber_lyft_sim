from flask import Blueprint, render_template, send_from_directory
import os
import pandas as pd

from trip_manager_dashboard import TripController, kpis, generate_dashboard_charts, build_trip_map

dashboard_home = Blueprint("dashboard_home", __name__)


@dashboard_home.route("/dashboard")
def dashboard():
    """
    Show the Trip Manager analytics dashboard:
    - KPIs (total trips, revenue, etc.)
    - Three charts (trips/day, trips by fare type, revenue/day)
    - Link to interactive Folium map
    """
    ctl = TripController()
    df = ctl.trips_df()

    if not df.empty:
        df["date"] = df["created_at"].dt.date
        df["fare"] = pd.to_numeric(df["fare"], errors="coerce").fillna(0.0)
        df["distance"] = (
            pd.to_numeric(df["distance"], errors="coerce").fillna(0).astype(int)
        )

    metrics = kpis(df)

    # Generate and save charts into static/ so the template can load them
    generate_dashboard_charts(df, output_dir="static")

    # Build / update the Folium map in static/
    build_trip_map(df, html_path=os.path.join("static", "dashboard_map.html"))

    return render_template("dashboard.html", kpi=metrics)


@dashboard_home.route("/dashboard/map")
def dashboard_map():
    """
    Serve the interactive Folium map HTML from static/.
    """
    return send_from_directory("static", "dashboard_map.html")

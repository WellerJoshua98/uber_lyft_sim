from flask import Blueprint, render_template_string, send_file
import pandas as pd

from trip_manager_dashboard import TripController, kpis, build_trip_map, generate_dashboard_charts

dashboard_home = Blueprint("dashboard_home", __name__)

@dashboard_home.route("/dashboard")
def dashboard():
    """
    Simple dashboard UI page:
    - pulls trips from DB via TripController
    - computes KPIs
    - regenerates dashboard_map.html
    """
    ctl = TripController()
    df = ctl.trips_df()

    if not df.empty:
        df["date"] = df["created_at"].dt.date
        df["fare"] = pd.to_numeric(df["fare"], errors="coerce").fillna(0.0)
        df["distance"] = (
            pd.to_numeric(df["distance"], errors="coerce").fillna(0).astype(int)
        )

    stats = kpis(df)
    # Rebuild the map so it's up to date with current trips
    build_trip_map(df, "dashboard_map.html")

    html = """
    <html>
      <head>
        <title>Trip Dashboard</title>
      </head>
      <body>
        <h1>Trip Dashboard</h1>
        <h2>Key Metrics</h2>
        <ul>
          <li>Total trips: {{ stats.trips }}</li>
          <li>Completed trips: {{ stats.completed }}</li>
          <li>Average fare: ${{ stats.avg_fare }}</li>
          <li>Total revenue: ${{ stats.total_revenue }}</li>
          <li>Average distance (km): {{ stats.avg_distance_km }}</li>
        </ul>
        <p><a href="/dashboard/map">Open interactive trip map</a></p>
      </body>
    </html>
    """
    return render_template_string(html, stats=stats)


@dashboard_home.route("/dashboard/map")
def dashboard_map():
    """
    Serve the generated Folium HTML map.
    """
    return send_file("dashboard_map.html")


@dashboard_home.route("/dashboard")
def dashboard():
    df = ctl.trips_df()
    if not df.empty:
        df["fare"] = pd.to_numeric(df["fare"], errors="coerce").fillna(0.0)
        df["distance"] = pd.to_numeric(df["distance"], errors="coerce").fillna(0).astype(int)

    metrics = kpis(df)

    #  generate charts into static/
    generate_dashboard_charts(df)

    #  update the map HTML
    map_path = build_trip_map(df, "dashboard_map.html")

    return render_template(
        "dashboard.html",
        metrics=metrics,
        map_url="/dashboard/map",
    )


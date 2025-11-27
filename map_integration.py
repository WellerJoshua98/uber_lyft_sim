"""
Map service integration using OpenRouteService API.
Handles geocoding and route calculation.
"""
import requests
from typing import Optional, Tuple, Dict, List
import os

# Try to load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, use regular environment variables


class MapService:
    """
    Service for interacting with OpenRouteService API.
    Provides geocoding and routing capabilities.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize map service with API key.
        
        Args:
            api_key: OpenRouteService API key. If None, reads from ORS_API_KEY env variable.
        """
        self.api_key = api_key or os.getenv("ORS_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouteService API key required. "
                           "Set ORS_API_KEY environment variable or pass api_key parameter.")
        
        self.base_url = "https://api.openrouteservice.org"
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
    
    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert an address to coordinates (latitude, longitude).
        
        Args:
            address: Address string to geocode
            
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        url = f"{self.base_url}/geocode/search"
        params = {
            "api_key": self.api_key,
            "text": address,
            "size": 1  # Get only the best match
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("features") and len(data["features"]) > 0:
                coords = data["features"][0]["geometry"]["coordinates"]
                # OpenRouteService returns [longitude, latitude]
                return (coords[1], coords[0])
            
            return None
        
        except requests.exceptions.RequestException as e:
            print(f"Geocoding error: {e}")
            return None
    
    def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """
        Convert coordinates to an address.
        
        Args:
            lat: Latitude
            lon: Longitude
            
        Returns:
            Address string or None if reverse geocoding fails
        """
        url = f"{self.base_url}/geocode/reverse"
        params = {
            "api_key": self.api_key,
            "point.lat": lat,
            "point.lon": lon,
            "size": 1
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("features") and len(data["features"]) > 0:
                return data["features"][0]["properties"]["label"]
            
            return None
        
        except requests.exceptions.RequestException as e:
            print(f"Reverse geocoding error: {e}")
            return None
    
    def get_route(self, start_coords: Tuple[float, float], 
                  end_coords: Tuple[float, float],
                  profile: str = "driving-car") -> Optional[Dict]:
        """
        Calculate route between two coordinates.
        
        Args:
            start_coords: (latitude, longitude) of start point
            end_coords: (latitude, longitude) of end point
            profile: Routing profile (driving-car, cycling-regular, foot-walking)
            
        Returns:
            Dict with route information or None if routing fails
        """
        url = f"{self.base_url}/v2/directions/{profile}"
        
        # OpenRouteService expects [longitude, latitude]
        coordinates = [
            [start_coords[1], start_coords[0]],
            [end_coords[1], end_coords[0]]
        ]
        
        body = {
            "coordinates": coordinates,
            "instructions": True,
            "units": "km"
        }
        
        try:
            response = requests.post(url, json=body, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("routes") and len(data["routes"]) > 0:
                route = data["routes"][0]
                summary = route["summary"]
                
                return {
                    "distance_km": summary["distance"] / 1000,  # Convert meters to km
                    "duration_min": summary["duration"] / 60,   # Convert seconds to minutes
                    "geometry": route.get("geometry"),
                    "bbox": route.get("bbox"),
                    "steps": route.get("segments", [{}])[0].get("steps", [])
                }
            
            return None
        
        except requests.exceptions.RequestException as e:
            print(f"Routing error: {e}")
            return None
    
    def calculate_trip_route(self, pickup_address: str, 
                            destination_address: str) -> Optional[Dict]:
        """
        Complete workflow: geocode addresses and calculate route.
        
        Args:
            pickup_address: Pickup address string
            destination_address: Destination address string
            
        Returns:
            Dict with complete route information or None if any step fails
        """
        # Geocode pickup address
        pickup_coords = self.geocode(pickup_address)
        if not pickup_coords:
            print(f"Failed to geocode pickup address: {pickup_address}")
            return None
        
        # Geocode destination address
        dest_coords = self.geocode(destination_address)
        if not dest_coords:
            print(f"Failed to geocode destination address: {destination_address}")
            return None
        
        # Calculate route
        route_info = self.get_route(pickup_coords, dest_coords)
        if not route_info:
            print(f"Failed to calculate route")
            return None
        
        # Add coordinate information
        route_info["pickup_coords"] = pickup_coords
        route_info["destination_coords"] = dest_coords
        route_info["pickup_address"] = pickup_address
        route_info["destination_address"] = destination_address
        
        return route_info
    
    def get_map_url(self, pickup_coords: Tuple[float, float], 
                    dest_coords: Tuple[float, float]) -> str:
        """
        Generate a URL to view the route on OpenRouteService maps.
        
        Args:
            pickup_coords: (latitude, longitude) of pickup
            dest_coords: (latitude, longitude) of destination
            
        Returns:
            URL string for viewing the route
        """
        return (f"https://maps.openrouteservice.org/directions?"
                f"n1={pickup_coords[0]}&n2={pickup_coords[1]}&"
                f"n3={dest_coords[0]}&n4={dest_coords[1]}&"
                f"b=0&c=0&k1=en-US&k2=km")


class MockMapService(MapService):
    """
    Mock map service for testing without API calls.
    Returns simulated data.
    """
    
    def __init__(self):
        """Initialize mock service without requiring API key"""
        self.api_key = "mock_key"
        self.base_url = "mock"
        self.headers = {}
    
    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """Return mock coordinates based on address hash"""
        # Simple mock: use hash of address to generate consistent coordinates
        hash_val = hash(address)
        lat = 40.7 + (hash_val % 100) / 1000
        lon = -74.0 + (hash_val % 100) / 1000
        return (lat, lon)
    
    def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Return mock address"""
        return f"{int(lat * 100)} Main St, New York, NY"
    
    def get_route(self, start_coords: Tuple[float, float], 
                  end_coords: Tuple[float, float],
                  profile: str = "driving-car") -> Optional[Dict]:
        """Return mock route information"""
        # Calculate simple distance using Pythagorean approximation
        lat_diff = end_coords[0] - start_coords[0]
        lon_diff = end_coords[1] - start_coords[1]
        distance_deg = (lat_diff**2 + lon_diff**2) ** 0.5
        distance_km = distance_deg * 111  # Rough conversion: 1 degree ≈ 111 km
        
        # Estimate duration (assuming 40 km/h average)
        duration_min = (distance_km / 40) * 60
        
        return {
            "distance_km": distance_km,
            "duration_min": duration_min,
            "geometry": None,
            "bbox": None,
            "steps": []
        }
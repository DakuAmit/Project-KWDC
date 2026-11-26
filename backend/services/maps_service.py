"""
Google Maps Platform Service for KTM-WDC
Supports:
- Address Geocoding (Nepal region bias)
- Places Autocomplete predictions
- Driving Road Distance & ETA via Google Distance Matrix API (with clean Haversine fallback)
"""
import json
import math
import urllib.parse
import urllib.request
from typing import Optional, Dict, Any, List, Tuple
from backend.config import settings, get_google_maps_key


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def geocode_address(address: str) -> Optional[Dict[str, Any]]:
    key = get_google_maps_key() or settings.GOOGLE_MAPS_API_KEY
    if not key or not address or len(address.strip()) < 3:
        return None
    try:
        query = urllib.parse.urlencode({
            "address": f"{address.strip()}, Nepal" if "nepal" not in address.lower() else address.strip(),
            "region": "np",
            "key": key,
        })
        url = f"https://maps.googleapis.com/maps/api/geocode/json?{query}"
        with urllib.request.urlopen(url, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == "OK" and data.get("results"):
            top = data["results"][0]
            loc = top["geometry"]["location"]
            return {
                "lat": float(loc["lat"]),
                "lng": float(loc["lng"]),
                "formatted_address": top.get("formatted_address", address),
                "source": "google_geocoding"
            }
    except Exception as e:
        print("[MAPS GEOCODE NOTICE]", e)
    return None


def places_autocomplete(query_text: str) -> List[Dict[str, Any]]:
    key = get_google_maps_key() or settings.GOOGLE_MAPS_API_KEY
    if not key or not query_text or len(query_text.strip()) < 2:
        return []
    try:
        params = urllib.parse.urlencode({
            "input": query_text.strip(),
            "components": "country:np",
            "key": key,
        })
        url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?{params}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") in ("OK", "ZERO_RESULTS"):
            return [
                {
                    "description": p.get("description"),
                    "place_id": p.get("place_id")
                }
                for p in (data.get("predictions") or [])[:6]
            ]
    except Exception as e:
        print("[MAPS PLACES NOTICE]", e)
    return []


def calculate_road_distance(
    origin: str,
    destination: str,
    origin_coords: Optional[Tuple[float, float]] = None,
    dest_coords: Optional[Tuple[float, float]] = None,
) -> Dict[str, Any]:
    key = get_google_maps_key() or settings.GOOGLE_MAPS_API_KEY

    if not origin_coords and origin:
        g1 = geocode_address(origin)
        if g1:
            origin_coords = (g1["lat"], g1["lng"])
    if not dest_coords and destination:
        g2 = geocode_address(destination)
        if g2:
            dest_coords = (g2["lat"], g2["lng"])

    if key and (origin or origin_coords) and (destination or dest_coords):
        orig_param = f"{origin_coords[0]},{origin_coords[1]}" if origin_coords else origin
        dest_param = f"{dest_coords[0]},{dest_coords[1]}" if dest_coords else destination
        try:
            params = urllib.parse.urlencode({
                "origins": orig_param,
                "destinations": dest_param,
                "mode": "driving",
                "region": "np",
                "key": key,
            })
            url = f"https://maps.googleapis.com/maps/api/distancematrix/json?{params}"
            with urllib.request.urlopen(url, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "OK":
                el = data["rows"][0]["elements"][0]
                if el.get("status") == "OK":
                    meters = float(el["distance"]["value"])
                    km = round(max(1.0, meters / 1000.0), 1)
                    dur_text = el.get("duration", {}).get("text", "25 mins")
                    return {
                        "distance_km": km,
                        "duration_text": dur_text,
                        "origin_lat": origin_coords[0] if origin_coords else 27.7172,
                        "origin_lng": origin_coords[1] if origin_coords else 85.3240,
                        "dest_lat": dest_coords[0] if dest_coords else 27.6937,
                        "dest_lng": dest_coords[1] if dest_coords else 85.2816,
                        "source": "google_distance_matrix"
                    }
        except Exception as e:
            print("[MAPS DISTANCE MATRIX NOTICE]", e)

    # Coordinate Haversine with Kathmandu winding road multiplier (1.32x)
    if origin_coords and dest_coords:
        straight = _haversine_km(origin_coords[0], origin_coords[1], dest_coords[0], dest_coords[1])
        km = round(max(1.5, straight * 1.32), 1)
        mins = max(10, int(round(km * 2.8)))
        return {
            "distance_km": km,
            "duration_text": f"~{mins} mins (est.)",
            "origin_lat": origin_coords[0],
            "origin_lng": origin_coords[1],
            "dest_lat": dest_coords[0],
            "dest_lng": dest_coords[1],
            "source": "haversine_estimate"
        }

    return {
        "distance_km": 12.0,
        "duration_text": "~35 mins (corridor est.)",
        "origin_lat": 27.7172,
        "origin_lng": 85.3240,
        "dest_lat": 27.6937,
        "dest_lng": 85.2816,
        "source": "default_corridor"
    }

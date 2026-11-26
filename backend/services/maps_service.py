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


def _clean_landmark_query(address: str) -> str:
    import re
    cleaned = re.sub(r"\b(near|opposite\s+to|opposite|beside|behind|in\s+front\s+of|next\s+to)\b", " ", address, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" ,")


def _google_geocode_once(query_text: str, key: str) -> Optional[Dict[str, Any]]:
    query = urllib.parse.urlencode({
        "address": f"{query_text}, Nepal" if "nepal" not in query_text.lower() else query_text,
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
            "formatted_address": top.get("formatted_address", query_text),
            "source": "google_geocoding"
        }
    return None


def geocode_address(address: str) -> Optional[Dict[str, Any]]:
    key = get_google_maps_key() or settings.GOOGLE_MAPS_API_KEY
    if not address or len(address.strip()) < 3:
        return None
    raw = address.strip()
    cleaned = _clean_landmark_query(raw)
    candidates = [raw]
    if cleaned and cleaned.lower() != raw.lower():
        candidates.append(cleaned)
    # Also try chunk-by-chunk (e.g. comma-separated parts) if compound landmark text misses
    if "," in cleaned:
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        if len(parts) > 1:
            candidates.append(", ".join(parts[1:]))

    if key:
        try:
            for cand in candidates:
                res = _google_geocode_once(cand, key)
                if res:
                    return res
        except Exception as e:
            print("[MAPS GEOCODE NOTICE]", e)

    # Fallback to Nominatim if Google key is absent or returns ZERO_RESULTS on informal landmark text
    try:
        for cand in candidates[:2]:
            q = urllib.parse.urlencode({
                "q": f"{cand}, Nepal" if "nepal" not in cand.lower() else cand,
                "format": "json",
                "limit": 1,
                "countrycodes": "np"
            })
            req = urllib.request.Request(
                f"https://nominatim.openstreetmap.org/search?{q}",
                headers={"User-Agent": "KTM-WDC-Logistics/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                nom = json.loads(resp.read().decode("utf-8"))
            if isinstance(nom, list) and nom:
                return {
                    "lat": float(nom[0]["lat"]),
                    "lng": float(nom[0]["lon"]),
                    "formatted_address": nom[0].get("display_name", cand),
                    "source": "nominatim_fallback"
                }
    except Exception as e:
        print("[MAPS NOMINATIM NOTICE]", e)
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

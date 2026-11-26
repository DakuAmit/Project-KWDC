"""
Google Maps Routing & Geocoding Router for KTM-WDC Web & React Native Mobile Apps
"""
from fastapi import APIRouter, Query
from typing import Optional
from backend.config import get_google_maps_key
from backend.services.maps_service import geocode_address, places_autocomplete, calculate_road_distance

router = APIRouter(prefix="/api/maps", tags=["Maps & Geolocation"])


@router.get("/status")
def get_maps_integration_status():
    key = get_google_maps_key()
    return {
        "google_maps_configured": bool(key),
        "mode": "google_maps_live" if key else "openstreetmap_fallback"
    }


@router.get("/autocomplete")
def autocomplete_places(q: str = Query(..., min_length=2)):
    return {"predictions": places_autocomplete(q)}


@router.get("/geocode")
def geocode_nepal_address(address: str = Query(..., min_length=3)):
    res = geocode_address(address)
    if not res:
        return {
            "found": False,
            "lat": 27.7172,
            "lng": 85.3240,
            "formatted_address": address,
            "source": "fallback_kathmandu"
        }
    return {"found": True, **res}


@router.get("/route-distance")
def get_route_distance(
    origin: str = Query(..., min_length=2),
    destination: str = Query(..., min_length=2),
    origin_lat: Optional[float] = None,
    origin_lng: Optional[float] = None,
    dest_lat: Optional[float] = None,
    dest_lng: Optional[float] = None,
):
    o_coords = (origin_lat, origin_lng) if (origin_lat is not None and origin_lng is not None) else None
    d_coords = (dest_lat, dest_lng) if (dest_lat is not None and dest_lng is not None) else None
    return calculate_road_distance(origin, destination, o_coords, d_coords)

from typing import Optional, Dict, Any

class KatahoService:
    @staticmethod
    def get_location_by_code(kataho_code: str) -> Optional[Dict[str, Any]]:
        """Resolve Kataho grid code to geographic details"""
        # Built-in fast lookup for common Kathmandu logistics zones
        zones = {
            "KTM-KLM-01": {"city": "Kathmandu", "area": "Kalimati", "latitude": 27.6823, "longitude": 85.3038},
            "KTM-BKM-02": {"city": "Lalitpur", "area": "Balkumari", "latitude": 27.6753, "longitude": 85.3230},
            "BRG-DRY-01": {"city": "Birgunj", "area": "Dry Port", "latitude": 27.0125, "longitude": 84.8765},
            "PKR-CHP-01": {"city": "Pokhara", "area": "Chipledhunga", "latitude": 28.2163, "longitude": 83.9875},
        }
        return zones.get(kataho_code.upper(), {
            "city": "Kathmandu",
            "area": "Kathmandu Metropolitan",
            "latitude": 27.7172,
            "longitude": 85.3240
        })

    @staticmethod
    def get_code_from_coords(latitude: float, longitude: float) -> str:
        # Simple grid hashing
        lat_part = int((latitude - 27.0) * 100)
        lon_part = int((longitude - 85.0) * 100)
        return f"KTM-G{abs(lat_part):02d}-{abs(lon_part):02d}"

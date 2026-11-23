"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Nepal Multi-Unit Conversion Service

Standard conversion factors based on official Nepali Land Measurement Standards:
1 Ropani = 16 Aana = 64 Paisa = 256 Daam = 5476.00 sq ft
1 Aana = 342.25 sq ft
1 Bigha = 20 Kattha = 400 Dhur = 72,900.00 sq ft
1 Kattha = 3645.00 sq ft
1 Dhur = 182.25 sq ft
1 Square Meter (sqm) = 10.7639 sq ft
"""

from typing import Dict, Any

SQFT_CONVERSIONS = {
    "sqft": 1.0,
    "sqm": 10.7639104,
    "aana": 342.25,
    "ropani": 5476.0,
    "kattha": 3645.0,
    "bigha": 72900.0,
    "dhur": 182.25
}

def to_sqft(value: float, unit: str, ceiling_height_ft: float = 10.0) -> float:
    """Converts any input unit to standard Square Feet (sqft)."""
    unit_lower = unit.lower().strip()
    if unit_lower == "cuft":
        height = max(ceiling_height_ft, 1.0)
        return round(value / height, 2)
    
    factor = SQFT_CONVERSIONS.get(unit_lower, 1.0)
    return round(value * factor, 2)

def from_sqft_to_all(sqft: float, ceiling_height_ft: float = 10.0) -> Dict[str, Any]:
    """Returns the given sqft represented in all Nepali traditional and international units."""
    height = max(ceiling_height_ft, 1.0)
    
    # Traditional Hill calculation (Ropani-Aana-Paisa-Daam)
    ropani_val = sqft / 5476.0
    aana_val = sqft / 342.25
    
    # Traditional Terai calculation (Bigha-Kattha-Dhur)
    bigha_val = sqft / 72900.0
    kattha_val = sqft / 3645.0
    dhur_val = sqft / 182.25
    
    return {
        "sqft": round(sqft, 2),
        "sqm": round(sqft / SQFT_CONVERSIONS["sqm"], 2),
        "cuft": round(sqft * height, 2),
        "aana": round(aana_val, 2),
        "ropani": round(ropani_val, 3),
        "bigha": round(bigha_val, 3),
        "kattha": round(kattha_val, 2),
        "dhur": round(dhur_val, 1),
        "ceiling_height_ft": height,
        "traditional_hill_str": f"{int(sqft // 5476)} Ropani, {round((sqft % 5476) / 342.25, 1)} Aana",
        "traditional_terai_str": f"{int(sqft // 72900)} Bigha, {round((sqft % 72900) / 3645, 1)} Kattha"
    }

def get_warehouse_usable_capacity(gross_sqft: float) -> Dict[str, float]:
    """
    Standard Warehouse Layout Logic:
    For e.g. 10,000 sq ft facility:
    - Gross billed area = 10,000 sq ft (what client contracts and pays for)
    - Net usable storage area = 9,000 sq ft (90% dedicated to cargo placement)
    - Walking / partition corridor allowance = 1,000 sq ft (10% dedicated to access corridors)
    """
    return {
        "gross_billed_sqft": round(gross_sqft, 2),
        "net_usable_sqft": round(gross_sqft * 0.90, 2),
        "corridor_allowance_sqft": round(gross_sqft * 0.10, 2)
    }

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
    """
    Converts any input unit to standard Square Feet (sqft).
    If unit is cubic feet (cuft), it divides by the clear ceiling height.
    """
    unit_lower = unit.lower().strip()
    if unit_lower == "cuft":
        height = max(ceiling_height_ft, 1.0)
        return round(value / height, 2)
    
    factor = SQFT_CONVERSIONS.get(unit_lower, 1.0)
    return round(value * factor, 2)

def from_sqft_to_all(sqft: float, ceiling_height_ft: float = 10.0) -> Dict[str, Any]:
    """
    Returns the given sqft represented in all Nepali traditional and international units.
    """
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

def calculate_10_percent_block(requested_sqft: float, total_warehouse_sqft: float) -> Dict[str, float]:
    """
    Enforces Rule 2: The 10% Floor Space Partitioning Rule
    Formula: Billed Space = Ceil(Requested Space / (Total Capacity * 0.10)) * (Total Capacity * 0.10)
    """
    import math
    
    block_size = max(total_warehouse_sqft * 0.10, 1.0)
    blocks_needed = math.ceil(requested_sqft / block_size)
    billed_sqft = min(blocks_needed * block_size, total_warehouse_sqft)
    
    # If requested is more than total, cap at total
    if requested_sqft >= total_warehouse_sqft:
        billed_sqft = total_warehouse_sqft
        blocks_needed = 10
        
    return {
        "requested_sqft": round(requested_sqft, 2),
        "total_warehouse_sqft": round(total_warehouse_sqft, 2),
        "block_size_sqft": round(block_size, 2),
        "blocks_allocated": int(blocks_needed),
        "billed_sqft": round(billed_sqft, 2),
        "space_utilization_pct": round((billed_sqft / total_warehouse_sqft) * 100, 1)
    }

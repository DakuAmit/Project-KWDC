"""
KTM-WDC Freight Tariff & Benchmark Pricing Engine
Calculates benchmark freight fare based on:
1. Base Flag Drop by Vehicle Category
2. Distance (KM) * Per-KM Fuel Rate * Fuel Multiplier
3. Cargo Weight Tier (Metric Tonnes * Rate per Tonne)
4. Admin-Configured Platform Margin & Net Driver Payout
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models import PlatformConfig, VehicleCategory


DEFAULT_CONFIG_DEFAULTS = {
    "platform_margin_percent": 10.0,
    "flag_drop_van_pickup": 1200.0,
    "flag_drop_mini_truck": 1800.0,
    "flag_drop_heavy_truck": 3200.0,
    "flag_drop_container_trailer": 5000.0,
    "rate_per_km_van_pickup": 65.0,
    "rate_per_km_mini_truck": 85.0,
    "rate_per_km_heavy_truck": 125.0,
    "rate_per_km_container_trailer": 175.0,
    "weight_rate_per_tonne": 150.0,
    "vat_rate_percent": 13.0,
    "fuel_multiplier": 1.0
}


def get_platform_config(db: Session) -> PlatformConfig:
    """
    Retrieves the active PlatformConfig from the database.
    If none exists, initializes and returns the default configuration.
    """
    cfg = db.query(PlatformConfig).filter(PlatformConfig.config_key == "DEFAULT_CONFIG").first()
    if not cfg:
        cfg = PlatformConfig(
            config_key="DEFAULT_CONFIG",
            **DEFAULT_CONFIG_DEFAULTS
        )
        try:
            db.add(cfg)
            db.commit()
            db.refresh(cfg)
        except Exception:
            db.rollback()
            cfg = db.query(PlatformConfig).filter(PlatformConfig.config_key == "DEFAULT_CONFIG").first()
    return cfg


def normalize_vehicle_category(cat: Optional[str]) -> str:
    """
    Normalizes human-readable or enum string into standardized tariff category keys.
    """
    if not cat:
        return "PICKUP_VAN"
    c = str(cat).upper().replace(" ", "_").replace("-", "_")
    if "CONTAINER" in c or "TRAILER" in c:
        return "CONTAINER_TRAILER"
    if "HEAVY" in c or "TIPPER" in c or "TRUCK_HEAVY" in c or "10T" in c:
        return "HEAVY_TRUCK"
    if "MINI" in c or "3.5" in c or "CANTER" in c:
        return "MINI_TRUCK"
    return "PICKUP_VAN"


def calculate_freight_benchmark(
    db: Session,
    vehicle_category: Optional[str] = "PICKUP_VAN",
    distance_km: float = 15.0,
    cargo_weight_kg: float = 1000.0
) -> Dict[str, Any]:
    """
    Calculates the benchmark fare, platform margin, and driver payout.
    Base Formula:
      Benchmark = Flag Drop(Category) + (KM * Per-KM Rate * Fuel Multiplier) + (Weight Tonnes * Rate/Tonne)
    """
    cfg = get_platform_config(db)
    cat_key = normalize_vehicle_category(vehicle_category)
    distance = max(1.0, float(distance_km or 1.0))
    weight_kg = max(0.0, float(cargo_weight_kg or 1000.0))
    weight_tonnes = weight_kg / 1000.0

    fuel_mult = float(cfg.fuel_multiplier or 1.0)
    margin_pct = float(cfg.platform_margin_percent or 10.0)

    # 1. Base Flag Drop
    if cat_key == "CONTAINER_TRAILER":
        flag_drop = float(cfg.flag_drop_container_trailer)
        rate_per_km = float(cfg.rate_per_km_container_trailer)
        cat_display = "Container / Trailer (> 10 Tonnes)"
    elif cat_key == "HEAVY_TRUCK":
        flag_drop = float(cfg.flag_drop_heavy_truck)
        rate_per_km = float(cfg.rate_per_km_heavy_truck)
        cat_display = "Heavy Commercial Truck (3.5T - 10 Tonnes)"
    elif cat_key == "MINI_TRUCK":
        flag_drop = float(cfg.flag_drop_mini_truck)
        rate_per_km = float(cfg.rate_per_km_mini_truck)
        cat_display = "Mini Truck / Canter (1.5T - 3.5 Tonnes)"
    else: # PICKUP_VAN
        flag_drop = float(cfg.flag_drop_van_pickup)
        rate_per_km = float(cfg.rate_per_km_van_pickup)
        cat_display = "Pickup / Tata Ace / Bolero (< 1.5 Tonnes)"

    # 2. Distance cost
    distance_cost = distance * rate_per_km * fuel_mult

    # 3. Cargo Weight cost
    weight_cost = weight_tonnes * float(cfg.weight_rate_per_tonne)

    # 4. Total Benchmark Fare
    benchmark_fare = round(flag_drop + distance_cost + weight_cost, 2)

    # 5. KTM-WDC Margin and Driver Payout
    platform_revenue = round(benchmark_fare * (margin_pct / 100.0), 2)
    driver_payout = round(benchmark_fare - platform_revenue, 2)

    return {
        "vehicle_category": cat_key,
        "vehicle_category_display": cat_display,
        "distance_km": round(distance, 1),
        "cargo_weight_kg": round(weight_kg, 1),
        "cargo_weight_tonnes": round(weight_tonnes, 2),
        "flag_drop_npr": flag_drop,
        "rate_per_km_npr": rate_per_km,
        "fuel_multiplier": fuel_mult,
        "distance_cost_npr": round(distance_cost, 2),
        "weight_cost_npr": round(weight_cost, 2),
        "benchmark_fare_npr": benchmark_fare,
        "platform_margin_percent": margin_pct,
        "platform_revenue_npr": platform_revenue,
        "driver_payout_npr": driver_payout,
        "formula_description": (
            f"Flag Drop (Rs. {flag_drop:,.0f}) + "
            f"Distance ({distance:.1f} KM × Rs. {rate_per_km:,.0f} × {fuel_mult} = Rs. {distance_cost:,.0f}) + "
            f"Weight ({weight_tonnes:.2f} Tonnes × Rs. {cfg.weight_rate_per_tonne:,.0f} = Rs. {weight_cost:,.0f})"
        )
    }

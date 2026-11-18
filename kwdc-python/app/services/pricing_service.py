from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models.finance import MarginTier

class PricingService:
    @staticmethod
    def get_margin(db: Session, distance: float, service_type: str = "dispatch") -> Dict[str, Any]:
        """Fetch matching margin tier from database based on distance"""
        tier = db.query(MarginTier).filter(
            MarginTier.service_type == service_type,
            MarginTier.is_active == True,
            MarginTier.min_distance <= distance
        ).order_by(MarginTier.min_distance.desc()).first()

        if tier:
            return {
                "name": tier.name,
                "type": tier.margin_type,
                "value": float(tier.margin_value)
            }
        
        # Default fallback tiers
        if distance <= 10:
            return {"name": "Short Distance (0-10km)", "type": "percentage", "value": 10.0}
        elif distance <= 50:
            return {"name": "Medium Distance (11-50km)", "type": "percentage", "value": 12.0}
        else:
            return {"name": "Long Distance (51km+)", "type": "percentage", "value": 15.0}

    @classmethod
    def calculate_dispatch_price(
        cls,
        db: Session,
        distance: float,
        vehicle_type: str = "truck",
        stops_count: int = 1
    ) -> Dict[str, Any]:
        # Vehicle base rates per km
        rates = {
            "bike": {"base": 150.0, "per_km": 25.0},
            "van": {"base": 300.0, "per_km": 40.0},
            "pickup": {"base": 450.0, "per_km": 55.0},
            "truck": {"base": 650.0, "per_km": 75.0},
            "heavy_truck": {"base": 1200.0, "per_km": 110.0},
        }
        veh_info = rates.get(vehicle_type.lower(), rates["truck"])
        
        raw_price = veh_info["base"] + (distance * veh_info["per_km"])
        # Stop handling surcharge
        stop_surcharge = max(0, stops_count - 1) * 150.0
        base_price = round(raw_price + stop_surcharge, 2)

        margin_info = cls.get_margin(db, distance, "dispatch")
        if margin_info["type"] == "flat":
            margin_amount = margin_info["value"]
            margin_pct = round((margin_amount / base_price) * 100, 2) if base_price > 0 else 0
        else:
            margin_pct = margin_info["value"]
            margin_amount = round(base_price * (margin_pct / 100.0), 2)

        subtotal = round(base_price + margin_amount, 2)
        vat_13_percent = round(subtotal * 0.13, 2)
        grand_total = round(subtotal + vat_13_percent, 2)

        explanation = (
            f"Distance: {distance} km with {vehicle_type}. Base driver fare: Rs. {base_price:,.2f}. "
            f"Admin Margin ({margin_info['name']}): Rs. {margin_amount:,.2f} ({margin_pct}%). "
            f"Subtotal: Rs. {subtotal:,.2f}. Nepal 13% VAT: Rs. {vat_13_percent:,.2f}. "
            f"Grand Total: Rs. {grand_total:,.2f}."
        )

        return {
            "distance": distance,
            "vehicle_type": vehicle_type,
            "base_price": base_price,
            "admin_margin_percentage": margin_pct,
            "admin_margin_amount": margin_amount,
            "subtotal": subtotal,
            "vat_13_percent": vat_13_percent,
            "grand_total": grand_total,
            "explanation": explanation
        }

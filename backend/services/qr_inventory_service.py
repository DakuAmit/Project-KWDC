"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
ISO/IEC 18004 Cryptographic QR Code Generator for Inventory

Supports:
- Individual Cartons / Boxes (BOX-KTM-...)
- Industrial Pallets (PLT-KTM-...)
- Sealed 20ft/40ft Shipping Containers (MSKU-...)
"""
import io
import base64
import qrcode
from typing import Dict, Any

def generate_unit_qr_code(
    unit_type: str,
    serial_number: str,
    sku_code: str,
    item_name: str,
    gross_weight_kg: float,
    bay_location: str
) -> Dict[str, Any]:
    qr_payload = (
        f"KWDC:{unit_type.upper()}|SN:{serial_number}|SKU:{sku_code}|"
        f"NAME:{item_name}|WT:{gross_weight_kg}KG|BAY:{bay_location}"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=2,
    )
    qr.add_data(qr_payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e293b", back_color="white")

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return {
        "unit_type": unit_type,
        "serial_number": serial_number,
        "sku_code": sku_code,
        "item_name": item_name,
        "gross_weight_kg": gross_weight_kg,
        "bay_location": bay_location,
        "qr_payload": qr_payload,
        "qr_data_uri": f"data:image/png;base64,{qr_base64}"
    }

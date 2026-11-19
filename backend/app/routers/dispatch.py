import uuid
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.logistics import DispatchOrder, DeliveryStop
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.pricing_service import PricingService
from app.services.invoice_service import InvoiceService
from app.schemas.dispatch import PriceCalculateRequest, PriceCalculateResponse, DispatchCreate

router = APIRouter(prefix="/dispatch", tags=["Freight Dispatch"])
from app.core.templates import templates

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    if user.is_admin:
        dispatches = db.query(DispatchOrder).order_by(DispatchOrder.id.desc()).all()
    elif user.is_driver:
        dispatches = db.query(DispatchOrder).filter(DispatchOrder.driver_id == user.id).all()
    else:
        dispatches = db.query(DispatchOrder).filter(DispatchOrder.client_id == user.id).all()

    return templates.TemplateResponse(
        request=request,
        name="dispatch/index.html",
        context={"user": user, "dispatches": dispatches}
    )

@router.get("/create", response_class=HTMLResponse)
def create_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request=request, name="dispatch/create.html", context={"user": user})

api_router = APIRouter(prefix="/api/dispatch", tags=["Dispatch API"])

@api_router.post("/calculate-price", response_model=PriceCalculateResponse)
@router.post("/calculate-price", response_model=PriceCalculateResponse)
def calculate_price_ajax(payload: PriceCalculateRequest, db: Session = Depends(get_db)):
    calc = PricingService.calculate_dispatch_price(
        db=db,
        distance=payload.distance,
        vehicle_type=payload.vehicle_type,
        stops_count=payload.stops_count
    )
    return calc

@api_router.post("/orders")
@api_router.post("")
def create_dispatch_json(payload: DispatchCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to book dispatch orders")

    stops_count = max(1, len(payload.stops))
    total_dist = float(payload.total_distance or 10.0)

    # Calculate pricing with 13% IRD VAT and admin distance margin tiers
    calc = PricingService.calculate_dispatch_price(
        db=db,
        distance=total_dist,
        vehicle_type=payload.vehicle_type or "truck",
        stops_count=stops_count
    )

    tracking_id = f"TRK-KWDC-{uuid.uuid4().hex[:6].upper()}"
    invoice_no = f"INV-DSP-{uuid.uuid4().hex[:6].upper()}"

    # Pick an active driver if available
    driver = db.query(User).filter(User.is_driver == True, User.is_active == True).first()

    wh_id = None
    if payload.warehouse_id:
        wh = db.query(Warehouse).filter(Warehouse.id == payload.warehouse_id).first()
        if wh:
            wh_id = wh.id

    order = DispatchOrder(
        client_id=user.id,
        driver_id=driver.id if driver else None,
        warehouse_id=wh_id,
        tracking_id=tracking_id,
        invoice_no=invoice_no,
        pickup_address=payload.pickup_address,
        pickup_latitude=payload.pickup_latitude,
        pickup_longitude=payload.pickup_longitude,
        pickup_contact_person=payload.pickup_contact_person or user.name,
        pickup_contact_phone=payload.pickup_contact_phone or user.phone or "9800000000",
        total_distance=total_dist,
        base_price=calc["base_price"],
        driver_earning=calc["base_price"],
        admin_margin=calc["admin_margin_amount"],
        tax_amount=calc["vat_13_percent"],
        grand_total=calc["grand_total"],
        bill_type=payload.bill_type or "regular",
        pan_number=payload.pan_number or "601234567",
        status="assigned" if driver else "pending",
        tracking_enabled=True
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Delivery Stops
    if payload.stops and len(payload.stops) > 0:
        for idx, s in enumerate(payload.stops, start=1):
            stop = DeliveryStop(
                dispatch_order_id=order.id,
                stop_number=idx,
                address=s.address,
                recipient_name=s.recipient_name,
                recipient_phone=s.recipient_phone,
                distance_price=round(calc["base_price"] / stops_count, 2),
                status="pending"
            )
            db.add(stop)
    else:
        # Default single drop-off stop
        stop = DeliveryStop(
            dispatch_order_id=order.id,
            stop_number=1,
            address=payload.delivery_address or "Ring Road Corridor, Kathmandu Valley",
            recipient_name=payload.recipient_name or "Consignee Manager",
            recipient_phone=payload.recipient_phone or "9801234567",
            distance_price=calc["base_price"],
            status="pending"
        )
        db.add(stop)

    db.commit()

    # Automatically generate official 13% IRD VAT Tax Invoice
    invoice = InvoiceService.create_dispatch_invoice(db, order, client_id=user.id)

    return {
        "status": "success",
        "message": f"Dispatch shipment #{tracking_id} confirmed and assigned",
        "dispatch": {
            "id": order.id,
            "tracking_id": order.tracking_id,
            "invoice_no": order.invoice_no,
            "pickup_address": order.pickup_address,
            "warehouse_id": order.warehouse_id,
            "total_distance": float(order.total_distance),
            "base_price": float(order.base_price),
            "admin_margin": float(order.admin_margin or 0),
            "tax_amount": float(order.tax_amount),
            "grand_total": float(order.grand_total),
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None
        },
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "subtotal": float(invoice.subtotal),
            "tax_amount": float(invoice.tax_amount),
            "grand_total": float(invoice.grand_total),
            "payment_status": invoice.payment_status
        }
    }

@api_router.get("/active-list")
def get_active_dispatches(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    query = db.query(DispatchOrder)
    if not (user.is_admin or user.role == "admin"):
        if user.role == "driver":
            query = query.filter(DispatchOrder.driver_id == user.id)
        else:
            query = query.filter(DispatchOrder.client_id == user.id)
            
    orders = query.order_by(DispatchOrder.id.desc()).limit(15).all()
    return [
        {
            "id": o.id,
            "tracking_id": o.tracking_id,
            "pickup_address": o.pickup_address,
            "total_distance": float(o.total_distance or 0),
            "grand_total": float(o.grand_total or 0),
            "status": o.status,
            "created_at": o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else None
        } for o in orders
    ]

@api_router.get("/{dispatch_id}")
def get_dispatch_json(dispatch_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if dispatch_id.isdigit():
        order = db.query(DispatchOrder).filter(
            (DispatchOrder.id == int(dispatch_id)) | (DispatchOrder.tracking_id == dispatch_id)
        ).first()
    else:
        order = db.query(DispatchOrder).filter(DispatchOrder.tracking_id == dispatch_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found")

    stops = db.query(DeliveryStop).filter(DeliveryStop.dispatch_order_id == order.id).order_by(DeliveryStop.stop_number.asc()).all()
    driver = db.query(User).filter(User.id == order.driver_id).first() if order.driver_id else None
    vehicle = db.query(Vehicle).filter(Vehicle.driver_id == order.driver_id).first() if order.driver_id else None

    dest_address = stops[0].address if stops else "Kathmandu Consignee"
    dest_name = stops[0].recipient_name if stops else "Consignee"
    dest_phone = stops[0].recipient_phone if stops else None

    return {
        "id": order.id,
        "tracking_id": order.tracking_id,
        "invoice_no": order.invoice_no,
        "pickup_address": order.pickup_address,
        "pickup_contact_person": order.pickup_contact_person,
        "pickup_contact_phone": order.pickup_contact_phone,
        "delivery_address": dest_address,
        "recipient_name": dest_name,
        "recipient_phone": dest_phone,
        "warehouse_id": order.warehouse_id,
        "total_distance": float(order.total_distance or 0),
        "grand_total": float(order.grand_total or 0),
        "status": order.status,
        "current_latitude": float(order.current_latitude or 27.7172),
        "current_longitude": float(order.current_longitude or 85.3240),
        "driver": {
            "name": driver.name,
            "phone": driver.phone,
            "vehicle": f"{vehicle.vehicle_type} ({vehicle.vehicle_number})" if vehicle else "Commercial Freight Carrier"
        } if driver else None,
        "stops": [
            {
                "stop_number": s.stop_number,
                "address": s.address,
                "recipient_name": s.recipient_name,
                "recipient_phone": s.recipient_phone,
                "status": s.status
            } for s in stops
        ]
    }

@router.post("/store")
def store(
    request: Request,
    pickup_address: str = Form(...),
    pickup_contact_person: str = Form(...),
    pickup_contact_phone: str = Form(...),
    vehicle_type: str = Form("truck"),
    total_distance: float = Form(10.0),
    stop_recipient_name: str = Form(...),
    stop_recipient_phone: str = Form(...),
    stop_address: str = Form(...),
    bill_type: str = Form("regular"),
    pan_number: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user_from_request(request, db)
    if not user:
        return RedirectResponse(url="/login")

    # Calculate fare with 13% IRD VAT
    calc = PricingService.calculate_dispatch_price(
        db=db,
        distance=total_distance,
        vehicle_type=vehicle_type,
        stops_count=1
    )

    tracking_id = f"TRK-KWDC-{uuid.uuid4().hex[:6].upper()}"
    invoice_no = f"INV-DSP-{uuid.uuid4().hex[:6].upper()}"

    # Pick an active driver if available
    driver = db.query(User).filter(User.is_driver == True).first()

    order = DispatchOrder(
        client_id=user.id,
        driver_id=driver.id if driver else None,
        tracking_id=tracking_id,
        invoice_no=invoice_no,
        pickup_address=pickup_address,
        pickup_contact_person=pickup_contact_person,
        pickup_contact_phone=pickup_contact_phone,
        total_distance=total_distance,
        base_price=calc["base_price"],
        driver_earning=calc["base_price"],
        admin_margin=calc["admin_margin_amount"],
        tax_amount=calc["vat_13_percent"],
        grand_total=calc["grand_total"],
        bill_type=bill_type,
        pan_number=pan_number or "601234567",
        status="assigned" if driver else "pending"
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Add Delivery Stop
    stop = DeliveryStop(
        dispatch_order_id=order.id,
        stop_number=1,
        address=stop_address,
        recipient_name=stop_recipient_name,
        recipient_phone=stop_recipient_phone,
        distance_price=calc["base_price"],
        status="pending"
    )
    db.add(stop)
    db.commit()

    # Automatically generate 13% IRD VAT Tax Invoice
    InvoiceService.create_dispatch_invoice(db, order, client_id=user.id)

    return RedirectResponse(url=f"/dispatch/track/{order.id}", status_code=302)

@router.get("/track/{dispatch_id}", response_class=HTMLResponse)
def track_dispatch(dispatch_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_request(request, db)
    order = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found")
    return templates.TemplateResponse(
        request=request,
        name="dispatch/track.html",
        context={"user": user, "dispatch": order}
    )

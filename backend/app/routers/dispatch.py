import uuid
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_from_request
from app.models.logistics import DispatchOrder, DeliveryStop
from app.models.user import User
from app.services.pricing_service import PricingService
from app.services.invoice_service import InvoiceService
from app.schemas.dispatch import PriceCalculateRequest, PriceCalculateResponse

router = APIRouter(prefix="/dispatch", tags=["Freight Dispatch"])
templates = Jinja2Templates(directory="app/templates")

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

@router.post("/calculate-price", response_model=PriceCalculateResponse)
def calculate_price_ajax(payload: PriceCalculateRequest, db: Session = Depends(get_db)):
    calc = PricingService.calculate_dispatch_price(
        db=db,
        distance=payload.distance,
        vehicle_type=payload.vehicle_type,
        stops_count=payload.stops_count
    )
    return calc

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

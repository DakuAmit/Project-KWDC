"""
Persistent Media Upload Router for KTM-WDC Web & React Native Mobile Apps.
Stores uploaded photos (Driver KYC, Citizenship/NID, Property Photos, Machinery, e-POD)
in the PostgreSQL `media_assets` ledger and returns stable `/api/uploads/media/{id}` URLs
that fit within VARCHAR(500) columns and persist across Vercel serverless containers.
"""
import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from backend.database import get_db
from backend.models import MediaAsset, User
from backend.auth_utils import get_current_user

router = APIRouter(prefix="/api/uploads", tags=["Media Uploads"])

MAX_IMAGE_BYTES = 1_500_000  # 1.5 MB limit per photo


class Base64UploadRequest(BaseModel):
    filename: str = "upload.jpg"
    content_type: Optional[str] = "image/jpeg"
    data_base64: str


@router.post("/image")
async def upload_multipart_image(
    file: UploadFile = File(...),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 1.5 MB limit. Please compress or resize before upload.")

    b64 = base64.b64encode(raw).decode("ascii")
    asset = MediaAsset(
        uploader_id=current_user.id if current_user else None,
        filename=file.filename or "photo.jpg",
        content_type=file.content_type or "image/jpeg",
        data_base64=b64
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return {
        "asset_id": asset.id,
        "url": f"/api/uploads/media/{asset.id}",
        "filename": asset.filename
    }


@router.post("/image-base64")
def upload_base64_image(
    payload: Base64UploadRequest,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    raw_b64 = payload.data_base64.strip()
    ctype = payload.content_type or "image/jpeg"
    if raw_b64.startswith("data:") and "," in raw_b64:
        header, raw_b64 = raw_b64.split(",", 1)
        if ":" in header and ";" in header:
            ctype = header.split(":", 1)[1].split(";", 1)[0]

    try:
        decoded = base64.b64decode(raw_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image payload.")

    if len(decoded) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 1.5 MB limit.")

    asset = MediaAsset(
        uploader_id=current_user.id if current_user else None,
        filename=payload.filename,
        content_type=ctype,
        data_base64=raw_b64
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return {
        "asset_id": asset.id,
        "url": f"/api/uploads/media/{asset.id}",
        "filename": asset.filename
    }


@router.get("/media/{asset_id}")
def get_uploaded_media(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found.")
    try:
        raw = base64.b64decode(asset.data_base64)
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupt media asset.")
    return Response(content=raw, media_type=asset.content_type or "image/jpeg")

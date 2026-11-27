"""
Cloud Storage & Persistent Media Upload Router for KTM-WDC Web & Mobile Apps.
Supports:
- Warehouse Gallery Photos & Walkthrough Videos (MP4/MOV/WebM)
- Property Owner, Client & Driver KYC Documents (PDF / JPG / PNG)
- Commercial Invoices, Packing Lists & Stock Manifests (PDF / XLSX / CSV / DOCX / Images)
- Heavy Equipment & Delivery e-POD Proofs

Routes bytes automatically to Supabase Cloud Storage CDN when `SUPABASE_SERVICE_ROLE_KEY`
is configured, with seamless PostgreSQL `MediaAsset` fallback when running offline/local.
"""
import base64
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.models import MediaAsset, User
from backend.auth_utils import get_current_user, require_user
from backend.services.cloud_storage import (
    get_storage_status,
    is_allowed_content_type,
    upload_bytes_to_supabase,
    create_supabase_signed_upload_url,
)

router = APIRouter(prefix="/api/uploads", tags=["Cloud Storage & Media Uploads"])

MAX_IMAGE_BYTES = 1_500_000        # 1.5 MB for legacy image endpoints
MAX_FALLBACK_FILE_BYTES = 4_000_000 # 4 MB Vercel/Postgres fallback limit


class Base64UploadRequest(BaseModel):
    filename: str = "upload.jpg"
    content_type: Optional[str] = "image/jpeg"
    category: Optional[str] = "GENERAL"
    data_base64: str


class SignedUrlRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    category: str = "GENERAL"
    file_size_bytes: Optional[int] = 0


class ConfirmCloudUploadRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    category: str = "GENERAL"
    storage_path: str
    cloud_url: str
    file_size_bytes: int = 0


def _persist_asset(
    db: Session,
    uploader_id: Optional[int],
    filename: str,
    content_type: str,
    category: str,
    raw_bytes: Optional[bytes],
    raw_b64: Optional[str] = None,
) -> MediaAsset:
    cloud_meta = None
    if raw_bytes is not None:
        try:
            cloud_meta = upload_bytes_to_supabase(raw_bytes, filename, content_type, category)
        except Exception as exc:
            print(f"[CLOUD STORAGE FALLBACK] {exc}")
            cloud_meta = None

    if cloud_meta:
        asset = MediaAsset(
            uploader_id=uploader_id,
            category=category,
            filename=filename,
            content_type=content_type,
            file_size_bytes=len(raw_bytes or b""),
            storage_provider=cloud_meta["storage_provider"],
            cloud_url=cloud_meta["cloud_url"],
            storage_path=cloud_meta["storage_path"],
            data_base64="",
        )
    else:
        b64 = raw_b64 or base64.b64encode(raw_bytes or b"").decode("ascii")
        asset = MediaAsset(
            uploader_id=uploader_id,
            category=category,
            filename=filename,
            content_type=content_type,
            file_size_bytes=len(raw_bytes or b""),
            storage_provider="POSTGRES_FALLBACK",
            cloud_url=None,
            storage_path=None,
            data_base64=b64,
        )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/status")
def storage_status():
    """Returns active cloud storage backend status (Supabase Storage vs Postgres fallback)."""
    return get_storage_status()


@router.post("/signed-url")
def request_signed_upload_url(
    payload: SignedUrlRequest,
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Returns a direct-to-cloud signed PUT URL when Supabase Storage is configured
    (enabling large warehouse walkthrough videos up to MAX_CLOUD_UPLOAD_MB without hitting Vercel limits).
    Otherwise indicates `direct_upload: false` so client uploads via `/api/uploads/file`.
    """
    if not is_allowed_content_type(payload.content_type, payload.filename):
        raise HTTPException(status_code=400, detail="Unsupported file format. Upload photos, videos, PDFs, or spreadsheets.")

    try:
        signed = create_supabase_signed_upload_url(payload.filename, payload.content_type, payload.category)
    except Exception as exc:
        print(f"[CLOUD SIGNED URL FALLBACK] {exc}")
        signed = None

    if signed:
        return signed

    return {
        "provider": "POSTGRES_FALLBACK",
        "direct_upload": False,
        "fallback_endpoint": "/api/uploads/file",
        "max_fallback_bytes": MAX_FALLBACK_FILE_BYTES,
    }


@router.post("/confirm")
def confirm_direct_cloud_upload(
    payload: ConfirmCloudUploadRequest,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Registers a directly uploaded cloud file in `media_assets` and returns unified URL."""
    asset = MediaAsset(
        uploader_id=current_user.id if current_user else None,
        category=payload.category.upper(),
        filename=payload.filename,
        content_type=payload.content_type,
        file_size_bytes=payload.file_size_bytes,
        storage_provider="SUPABASE_STORAGE",
        cloud_url=payload.cloud_url,
        storage_path=payload.storage_path,
        data_base64="",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {
        "asset_id": asset.id,
        "url": payload.cloud_url,
        "proxy_url": f"/api/uploads/media/{asset.id}",
        "storage_provider": asset.storage_provider,
        "category": asset.category,
        "filename": asset.filename,
    }


@router.post("/file")
async def upload_general_file(
    file: UploadFile = File(...),
    category: str = Form("GENERAL"),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Universal multipart uploader for Photos, Videos (MP4/MOV/WebM), KYC PDFs, and Packing Lists/Invoices.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    ctype = file.content_type or "application/octet-stream"
    fname = file.filename or "document"
    if not is_allowed_content_type(ctype, fname):
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    status_info = get_storage_status()
    max_allowed = (status_info["max_file_mb"] * 1024 * 1024) if status_info["cloud_enabled"] else MAX_FALLBACK_FILE_BYTES
    if len(raw) > max_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds {round(max_allowed / (1024 * 1024), 1)} MB limit under {status_info['provider']}.",
        )

    asset = _persist_asset(
        db=db,
        uploader_id=current_user.id if current_user else None,
        filename=fname,
        content_type=ctype,
        category=category.upper(),
        raw_bytes=raw,
    )
    return {
        "asset_id": asset.id,
        "url": asset.cloud_url or f"/api/uploads/media/{asset.id}",
        "proxy_url": f"/api/uploads/media/{asset.id}",
        "storage_provider": asset.storage_provider,
        "category": asset.category,
        "filename": asset.filename,
        "content_type": asset.content_type,
        "file_size_bytes": asset.file_size_bytes,
    }


@router.post("/image")
async def upload_multipart_image(
    file: UploadFile = File(...),
    category: str = Form("GENERAL"),
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 1.5 MB limit. Please compress or resize before upload.")

    asset = _persist_asset(
        db=db,
        uploader_id=current_user.id if current_user else None,
        filename=file.filename or "photo.jpg",
        content_type=file.content_type or "image/jpeg",
        category=category.upper(),
        raw_bytes=raw,
    )
    return {
        "asset_id": asset.id,
        "url": asset.cloud_url or f"/api/uploads/media/{asset.id}",
        "storage_provider": asset.storage_provider,
        "filename": asset.filename,
    }


@router.post("/image-base64")
def upload_base64_image(
    payload: Base64UploadRequest,
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
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

    asset = _persist_asset(
        db=db,
        uploader_id=current_user.id if current_user else None,
        filename=payload.filename,
        content_type=ctype,
        category=(payload.category or "GENERAL").upper(),
        raw_bytes=decoded,
        raw_b64=raw_b64,
    )
    return {
        "asset_id": asset.id,
        "url": asset.cloud_url or f"/api/uploads/media/{asset.id}",
        "storage_provider": asset.storage_provider,
        "filename": asset.filename,
    }


@router.get("/my-files")
def list_my_uploaded_files(
    category: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    q = db.query(MediaAsset).filter(MediaAsset.uploader_id == current_user.id)
    if category:
        q = q.filter(MediaAsset.category == category.upper())
    assets = q.order_by(MediaAsset.created_at.desc()).limit(50).all()
    return [
        {
            "id": a.id,
            "filename": a.filename,
            "category": getattr(a, "category", "GENERAL"),
            "content_type": a.content_type,
            "file_size_bytes": getattr(a, "file_size_bytes", 0) or 0,
            "storage_provider": getattr(a, "storage_provider", "POSTGRES_FALLBACK"),
            "url": getattr(a, "cloud_url", None) or f"/api/uploads/media/{a.id}",
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
        }
        for a in assets
    ]


@router.get("/media/{asset_id}")
def get_uploaded_media(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Media asset not found.")
    if getattr(asset, "cloud_url", None):
        return RedirectResponse(url=asset.cloud_url, status_code=307)
    try:
        raw = base64.b64decode(asset.data_base64 or "")
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupt media asset.")
    return Response(content=raw, media_type=asset.content_type or "application/octet-stream")

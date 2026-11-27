"""
Kathmandu Warehousing & Distribution Center (KTM-WDC)
Cloud Object Storage Service (Supabase Storage REST + Signed Upload URLs)

Supports:
- Warehouse Photos & Walkthrough Videos (MP4/MOV/WebM up to MAX_CLOUD_UPLOAD_MB)
- KYC Identity Documents (Citizenship, NID, Company Registration, PAN/VAT PDFs/Images)
- Invoices, Packing Lists & Customs Declarations (PDF, XLSX, CSV, DOCX, Images)
- Heavy Equipment & Delivery e-POD Proofs

Behavior:
- When `SUPABASE_SERVICE_ROLE_KEY` is configured, files are uploaded to Supabase Storage
  bucket (`SUPABASE_STORAGE_BUCKET`, default `kwdc-media`), with direct browser/mobile
  signed-PUT URLs so large videos bypass Vercel's 4.5 MB serverless function limit.
- When `SUPABASE_SERVICE_ROLE_KEY` is not set yet, seamlessly falls back to PostgreSQL
  `MediaAsset` storage (up to 4 MB per direct file) so local & test workflows never break.
"""
import re
import uuid
from typing import Optional, Dict, Any
from urllib.parse import quote
import requests
from backend.config import settings

ALLOWED_MIME_PREFIXES = ("image/", "video/")
ALLOWED_DOC_MIMES = {
    "application/pdf",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",
}

_BUCKET_CHECKED = False


def get_storage_status() -> Dict[str, Any]:
    cloud_enabled = bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)
    return {
        "provider": "SUPABASE_STORAGE" if cloud_enabled else "POSTGRES_FALLBACK",
        "cloud_enabled": cloud_enabled,
        "supabase_url": settings.SUPABASE_URL if cloud_enabled else None,
        "bucket": settings.SUPABASE_STORAGE_BUCKET,
        "max_file_mb": settings.MAX_CLOUD_UPLOAD_MB if cloud_enabled else 4,
    }


def _safe_filename(filename: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (filename or "file.bin").strip())
    return base[:120] or "file.bin"


def build_storage_path(category: str, filename: str) -> str:
    cat_slug = re.sub(r"[^a-z0-9_-]+", "_", (category or "general").lower()).strip("_") or "general"
    unique = uuid.uuid4().hex[:12]
    return f"{cat_slug}/{unique}_{_safe_filename(filename)}"


def is_allowed_content_type(content_type: str, filename: str = "") -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    if any(ct.startswith(p) for p in ALLOWED_MIME_PREFIXES) or ct in ALLOWED_DOC_MIMES:
        return True
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    return ext in {"jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "webm", "avi", "mkv", "pdf", "csv", "xls", "xlsx", "doc", "docx"}


def _supabase_headers(content_type: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def ensure_supabase_bucket() -> None:
    global _BUCKET_CHECKED
    if _BUCKET_CHECKED or not settings.SUPABASE_SERVICE_ROLE_KEY:
        return
    try:
        resp = requests.get(
            f"{settings.SUPABASE_URL}/storage/v1/bucket/{settings.SUPABASE_STORAGE_BUCKET}",
            headers=_supabase_headers(),
            timeout=8,
        )
        if resp.status_code == 404 or resp.status_code == 400:
            requests.post(
                f"{settings.SUPABASE_URL}/storage/v1/bucket",
                headers=_supabase_headers("application/json"),
                json={
                    "id": settings.SUPABASE_STORAGE_BUCKET,
                    "name": settings.SUPABASE_STORAGE_BUCKET,
                    "public": True,
                    "file_size_limit": settings.MAX_CLOUD_UPLOAD_MB * 1024 * 1024,
                },
                timeout=8,
            )
        _BUCKET_CHECKED = True
    except Exception:
        pass


def build_public_object_url(storage_path: str) -> str:
    encoded_path = quote(storage_path, safe="/")
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{encoded_path}"


def upload_bytes_to_supabase(
    raw_bytes: bytes,
    filename: str,
    content_type: str,
    category: str = "GENERAL",
) -> Optional[Dict[str, str]]:
    """Uploads raw bytes directly to Supabase Storage via REST API."""
    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        return None
    ensure_supabase_bucket()
    storage_path = build_storage_path(category, filename)
    encoded_path = quote(storage_path, safe="/")
    upload_endpoint = f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{encoded_path}"

    headers = _supabase_headers(content_type or "application/octet-stream")
    headers["x-upsert"] = "true"
    resp = requests.post(upload_endpoint, data=raw_bytes, headers=headers, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase Storage upload error ({resp.status_code}): {resp.text[:200]}")

    return {
        "storage_provider": "SUPABASE_STORAGE",
        "storage_path": storage_path,
        "cloud_url": build_public_object_url(storage_path),
    }


def create_supabase_signed_upload_url(
    filename: str,
    content_type: str,
    category: str = "GENERAL",
) -> Optional[Dict[str, Any]]:
    """
    Requests a short-lived signed upload URL from Supabase Storage so browsers and
    mobile apps can upload large videos/PDFs directly without passing through Vercel's 4.5MB limit.
    """
    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        return None
    ensure_supabase_bucket()
    storage_path = build_storage_path(category, filename)
    encoded_path = quote(storage_path, safe="/")
    sign_endpoint = f"{settings.SUPABASE_URL}/storage/v1/object/upload/sign/{settings.SUPABASE_STORAGE_BUCKET}/{encoded_path}"

    resp = requests.post(
        sign_endpoint,
        headers=_supabase_headers("application/json"),
        json={},
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase signed URL error ({resp.status_code}): {resp.text[:200]}")

    data = resp.json() or {}
    rel_url = data.get("url") or ""
    if rel_url.startswith("http"):
        signed_put_url = rel_url
    elif rel_url.startswith("/"):
        signed_put_url = f"{settings.SUPABASE_URL}/storage/v1{rel_url}" if not rel_url.startswith("/storage/v1") else f"{settings.SUPABASE_URL}{rel_url}"
    else:
        token = data.get("token", "")
        signed_put_url = f"{settings.SUPABASE_URL}/storage/v1/object/upload/sign/{settings.SUPABASE_STORAGE_BUCKET}/{encoded_path}?token={token}"

    return {
        "provider": "SUPABASE_STORAGE",
        "direct_upload": True,
        "method": "PUT",
        "upload_url": signed_put_url,
        "storage_path": storage_path,
        "cloud_url": build_public_object_url(storage_path),
        "content_type": content_type,
    }

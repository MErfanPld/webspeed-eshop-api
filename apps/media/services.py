from django.conf import settings
from django.core.files.base import ContentFile

from apps.core.errors import ApiError, bad_request, not_found
from apps.core.validators import sniff_image
from apps.stores.models import Store

from .models import MediaFile


def read_upload(upload, label: str = "فایل") -> tuple[bytes, str, str]:
    """Read an uploaded image; validate size and real type (magic bytes)."""
    if upload is None or not hasattr(upload, "read"):
        raise bad_request("فایلی ارسال نشده است")
    if upload.size == 0:
        raise bad_request("فایل خالی است")
    if upload.size > settings.MAX_UPLOAD_BYTES:
        raise ApiError(f"حداکثر حجم {label} ۵ مگابایت است", 413)
    data = upload.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ApiError(f"حداکثر حجم {label} ۵ مگابایت است", 413)
    kind = sniff_image(data)
    if not kind:
        raise bad_request("فقط تصاویر PNG، JPG، WEBP یا GIF مجاز هستند")
    return data, kind[0], kind[1]


def _safe_name(name: str, ext: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in "._ -") else "_" for c in (name or ""))[:120]
    return cleaned or f"image.{ext}"


def serialize(m: MediaFile) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "mime": m.mime,
        "size": m.size,
        "url": m.file.url,
        "createdAt": m.created_at.isoformat().replace("+00:00", "Z"),
    }


def upload(store: Store, file) -> MediaFile:
    data, mime, ext = read_upload(file)
    m = MediaFile(store=store, name=_safe_name(getattr(file, "name", ""), ext), mime=mime, size=len(data))
    m.file.save(f"upload.{ext}", ContentFile(data), save=False)
    m.save()
    return m


def delete(store: Store, media_id) -> None:
    m = MediaFile.objects.filter(store=store, id=media_id).first()
    if not m:
        raise not_found("فایل یافت نشد")
    m.file.delete(save=False)
    m.delete()

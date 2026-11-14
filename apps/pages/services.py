"""
Page business rules (ported from frontend src/server/services/pages.ts).
Every function takes the store explicitly — no cross-store access possible.
"""
import copy
import secrets
import time

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.blocks import validate_blocks
from apps.core.errors import bad_request, conflict, forbidden, not_found
from apps.core.validators import is_reserved_slug, is_valid_slug, normalize_slug, sanitize_urls
from apps.stores.models import Store

from .models import Page

SCHEMA_VERSION = 1
SITE_HEADER_ID = "site-header"
SITE_FOOTER_ID = "site-footer"
PROTECTED_KEYS = {"home", SITE_HEADER_ID, SITE_FOOTER_ID}
LAYOUT_SLUGS = {"header": "/_layout/header", "footer": "/_layout/footer"}
LAYOUT_TYPES = {"header", "footer"}
TYPES = {c.value for c in Page.Type}


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def serialize(page: Page) -> dict:
    """Frontend ManagedPage shape (camelCase)."""
    doc = page.doc or {}
    return {
        "schemaVersion": doc.get("schemaVersion", SCHEMA_VERSION),
        "id": page.key,
        "name": doc.get("name", ""),
        "slug": page.slug,
        "type": page.type,
        "status": page.status,
        "description": doc.get("description") or "",
        "seo": doc.get("seo") or None,
        "blocks": doc.get("blocks", []),
        "publishedBlocks": page.published_blocks if page.published_blocks is not None else None,
        "createdAt": _iso(page.created_at),
        "updatedAt": _iso(page.updated_at),
        "publishedAt": _iso(page.published_at),
    }


def public_serialize(page: Page) -> dict:
    """Published snapshot only — drafts never leave the server publicly."""
    data = serialize(page)
    data["blocks"] = []
    return data


def _clean_seo(raw):
    if not isinstance(raw, dict):
        return None
    out = {k: raw[k] for k in ("title", "description", "ogImage") if isinstance(raw.get(k), str)}
    out = sanitize_urls(out)
    return out or None


def _resolve_slug(page_type: str, slug) -> str:
    if page_type == "home":
        return "/"
    if page_type in LAYOUT_TYPES:
        return LAYOUT_SLUGS[page_type]
    s = normalize_slug(slug if isinstance(slug, str) else "")
    if not is_valid_slug(s) or s == "/":
        raise bad_request(f"آدرس نامعتبر است: {s}")
    if is_reserved_slug(s):
        raise bad_request(f"این مسیر سیستمی است و قابل استفاده نیست: {s}")
    return s


def _validated_doc(raw: dict, page_type: str) -> dict:
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise bad_request("اعتبارسنجی صفحه ناموفق: نام صفحه الزامی است")
    try:
        blocks = validate_blocks(raw.get("blocks", []))
    except ValueError as e:
        raise bad_request(f"اعتبارسنجی صفحه ناموفق: {e}") from None
    return {
        "schemaVersion": SCHEMA_VERSION,
        "name": name.strip()[:200],
        "description": raw.get("description") if isinstance(raw.get("description"), str) else "",
        "seo": _clean_seo(raw.get("seo")),
        "blocks": sanitize_urls(blocks),
    }


def _assert_slug_free(store: Store, slug: str, exclude_pk=None):
    qs = Page.objects.filter(store=store, slug=slug)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise conflict(f"این آدرس قبلاً استفاده شده: {slug}")


def list_pages(store: Store) -> list[Page]:
    return list(Page.objects.filter(store=store).order_by("-updated_at"))


def get_page(store: Store, key: str) -> Page:
    page = Page.objects.filter(store=store, key=key).first()
    if not page:
        raise not_found("صفحه یافت نشد")
    return page


def get_published(store: Store, key: str) -> Page | None:
    page = Page.objects.filter(store=store, key=key, status=Page.Status.PUBLISHED).first()
    return page if page and page.published_blocks else None


def get_published_by_slug(store: Store, slug: str) -> Page | None:
    page = (
        Page.objects.filter(store=store, slug=normalize_slug(slug), status=Page.Status.PUBLISHED)
        .exclude(type__in=LAYOUT_TYPES)
        .first()
    )
    return page if page and page.published_blocks else None


def _new_key(prefix="page") -> str:
    return f"{prefix}-{int(time.time() * 1000):x}-{secrets.token_hex(2)}"


@transaction.atomic
def create_page(store: Store, name, slug, page_type=None) -> Page:
    if not isinstance(name, str) or not name.strip():
        raise bad_request("نام صفحه الزامی است")
    ptype = page_type if page_type in {"landing", "content", "custom"} else "custom"
    final_slug = _resolve_slug(ptype, slug)
    _assert_slug_free(store, final_slug)
    doc = _validated_doc({"name": name, "blocks": []}, ptype)
    try:
        return Page.objects.create(store=store, key=_new_key(), slug=final_slug, type=ptype, doc=doc)
    except IntegrityError:
        raise conflict(f"این آدرس قبلاً استفاده شده: {final_slug}") from None


@transaction.atomic
def save_page(store: Store, key: str, raw) -> Page:
    """Save the working draft (blocks + meta). Never touches status/publishedBlocks."""
    if not isinstance(raw, dict) or raw.get("id") != key:
        raise bad_request("شناسه صفحه با آدرس مطابقت ندارد")
    page = Page.objects.select_for_update().filter(store=store, key=key).first()
    if not page:
        raise not_found("صفحه یافت نشد")
    ptype = page.type if page.key in PROTECTED_KEYS else raw.get("type", page.type)
    if ptype not in TYPES:
        raise bad_request("اعتبارسنجی صفحه ناموفق: Invalid page type")
    if page.key not in PROTECTED_KEYS and ptype in LAYOUT_TYPES | {"home"}:
        ptype = page.type
    slug = _resolve_slug(ptype, raw.get("slug"))
    _assert_slug_free(store, slug, exclude_pk=page.pk)
    page.doc = _validated_doc(raw, ptype)
    page.type = ptype
    page.slug = slug
    try:
        page.save()
    except IntegrityError:
        raise conflict(f"این آدرس قبلاً استفاده شده: {slug}") from None
    return page


def delete_page(store: Store, key: str):
    if key in PROTECTED_KEYS:
        raise forbidden("صفحات سیستمی قابل حذف نیستند")
    deleted, _ = Page.objects.filter(store=store, key=key).delete()
    if not deleted:
        raise not_found("صفحه یافت نشد")


def _reassign_ids(blocks):
    def walk(value):
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            out = {k: walk(v) for k, v in value.items()}
            if isinstance(out.get("id"), str):
                out["id"] = f"{out.get('type') or 'item'}-{int(time.time() * 1000):x}-{secrets.token_hex(3)}"
            return out
        return value

    return walk(copy.deepcopy(blocks))


@transaction.atomic
def duplicate_page(store: Store, key: str) -> Page:
    source = get_page(store, key)
    if source.type in LAYOUT_TYPES:
        raise bad_request("هدر و فوتر سراسری قابل تکرار نیستند")
    taken = set(Page.objects.filter(store=store).values_list("slug", flat=True))
    root = "/home" if source.slug == "/" else source.slug
    slug = f"{root}-copy"
    i = 2
    while slug in taken:
        slug = f"{root}-copy-{i}"
        i += 1
    doc = copy.deepcopy(source.doc)
    doc["name"] = f"{doc.get('name', '')} (کپی)"
    doc["blocks"] = _reassign_ids(doc.get("blocks", []))
    return Page.objects.create(
        store=store,
        key=f"{source.key}-copy-{int(time.time() * 1000):x}",
        slug=slug,
        type="landing" if source.type == "home" else source.type,
        status=Page.Status.DRAFT,
        doc=doc,
    )


@transaction.atomic
def publish_page(store: Store, key: str) -> Page:
    page = Page.objects.select_for_update().filter(store=store, key=key).first()
    if not page:
        raise not_found("صفحه یافت نشد")
    page.status = Page.Status.PUBLISHED
    page.published_blocks = copy.deepcopy(page.doc.get("blocks", []))
    page.published_at = timezone.now()
    page.save()
    return page


@transaction.atomic
def unpublish_page(store: Store, key: str) -> Page:
    page = Page.objects.select_for_update().filter(store=store, key=key).first()
    if not page:
        raise not_found("صفحه یافت نشد")
    page.status = Page.Status.DRAFT
    page.published_blocks = []
    page.published_at = None
    page.save()
    return page

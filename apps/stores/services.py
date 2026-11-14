from django.db import IntegrityError, transaction

from apps.core.errors import bad_request, conflict
from apps.core.validators import DOMAIN_RE, STORE_SLUG_RE, sanitize_urls

from .models import Store, StoreMember

SETTING_KEYS = {"tagline", "phone", "email", "address", "currency", "workingHours", "instagram"}


def serialize(store: Store) -> dict:
    return {
        "id": str(store.id),
        "name": store.name,
        "slug": store.slug,
        "domain": store.domain,
        "settings": store.settings or {},
        "createdAt": store.created_at.isoformat().replace("+00:00", "Z"),
    }


def public_info(store: Store) -> dict:
    s = store.settings or {}
    return {
        "id": str(store.id),
        "name": store.name,
        "tagline": s.get("tagline", ""),
        "phone": s.get("phone", ""),
        "email": s.get("email", ""),
        "address": s.get("address", ""),
        "workingHours": s.get("workingHours", ""),
        "instagram": s.get("instagram", ""),
        "payment": s.get("payment", {}),
        "shipping": s.get("shipping", {}),
    }


def _clean_domain(value) -> str | None:
    d = (value or "").strip().lower() if isinstance(value, str) else ""
    if d and not DOMAIN_RE.match(d):
        raise bad_request("دامنه نامعتبر است")
    return d or None


def _clean_settings(current: dict, patch) -> dict:
    if not isinstance(patch, dict):
        return current
    out = dict(current or {})
    for k in SETTING_KEYS:
        if isinstance(patch.get(k), str):
            out[k] = patch[k].strip()[:300]
    if isinstance(patch.get("payment"), dict):
        p = patch["payment"]
        out["payment"] = {k: str(p.get(k) or "").strip()[:60] for k in ("cardNumber", "cardHolder", "bank")}
    if isinstance(patch.get("shipping"), dict):
        s = patch["shipping"]

        def money(v):
            try:
                return max(0, int(v or 0))
            except (TypeError, ValueError):
                raise bad_request("مقدار هزینه ارسال نامعتبر است") from None

        out["shipping"] = {"flatRate": money(s.get("flatRate")), "freeOver": money(s.get("freeOver"))}
    return sanitize_urls(out)


@transaction.atomic
def create_store(owner, name, slug, domain=None) -> Store:
    from apps.core.seed import seed_store_content

    name = (name or "").strip() if isinstance(name, str) else ""
    slug = (slug or "").strip().lower() if isinstance(slug, str) else ""
    if not name:
        raise bad_request("نام فروشگاه الزامی است")
    if not STORE_SLUG_RE.match(slug):
        raise bad_request("شناسه فروشگاه فقط حروف انگلیسی کوچک، عدد و - (۲ تا ۴۰ کاراکتر)")
    domain = _clean_domain(domain)
    if Store.objects.filter(slug=slug).exists():
        raise conflict("این شناسه قبلاً استفاده شده")
    if domain and Store.objects.filter(domain=domain).exists():
        raise conflict("این دامنه قبلاً ثبت شده")
    try:
        store = Store.objects.create(name=name[:120], slug=slug, domain=domain, settings={"currency": "IRT"})
    except IntegrityError:
        raise conflict("این شناسه یا دامنه قبلاً استفاده شده") from None
    StoreMember.objects.create(store=store, user=owner, role=StoreMember.Role.OWNER)
    seed_store_content(store, with_sample_catalog=False)
    return store


@transaction.atomic
def update_store(store: Store, data: dict) -> Store:
    if "name" in data:
        name = data["name"].strip() if isinstance(data["name"], str) else ""
        if not name:
            raise bad_request("نام فروشگاه الزامی است")
        store.name = name[:120]
    if "domain" in data:
        domain = _clean_domain(data["domain"])
        if domain and Store.objects.filter(domain=domain).exclude(pk=store.pk).exists():
            raise conflict("این دامنه قبلاً ثبت شده")
        store.domain = domain
    if "settings" in data:
        store.settings = _clean_settings(store.settings, data["settings"])
    store.save()
    return store

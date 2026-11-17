"""
Store (tenant) resolution.

Admin requests: the store comes from the `X-Store-Id` header or the `ws_store`
cookie and MUST be one the user is a member of (otherwise the first one).
Public requests: the store comes from the storefront host — `X-Store-Host`
header (sent by the frontend), else the request Host:
  - a store's custom domain, or
  - <slug>.PLATFORM_DOMAIN (store subdomain)
With PLATFORM_DOMAIN set, unknown hosts are a 404 (never another store's
data). Without it (development), DEFAULT_STORE_SLUG or the first store.

Admin requests on a store host (subdomain / custom domain) are locked to that
store; the central panel host (panel.PLATFORM_DOMAIN) and development hosts
can switch between the user's stores.
"""
from dataclasses import dataclass

from django.conf import settings
from rest_framework.permissions import BasePermission

from apps.core.errors import ApiError, forbidden, not_found

from .models import Store, StoreMember, has_role


@dataclass
class AdminContext:
    user: object
    store: Store
    role: str
    memberships: list[StoreMember]

    def membership_payload(self):
        return [membership_dict(m) for m in self.memberships]


def membership_dict(m: StoreMember) -> dict:
    return {"storeId": str(m.store_id), "storeName": m.store.name, "storeSlug": m.store.slug, "role": m.role}


def resolve_admin(request, min_role: str = "editor") -> AdminContext:
    user = request.user
    if not user or not user.is_authenticated:
        raise ApiError("ابتدا وارد شوید", 401)
    memberships = list(StoreMember.objects.filter(user=user).select_related("store").order_by("store__created_at"))
    if not memberships:
        raise forbidden("به هیچ فروشگاهی دسترسی ندارید")
    host_store = store_for_host(request_host(request))
    if host_store is not None:
        # Store subdomain / custom domain: only that store, never another one
        m = next((x for x in memberships if x.store_id == host_store.id), None)
        if m is None:
            raise forbidden("به پنل این فروشگاه دسترسی ندارید")
    else:
        wanted = request.headers.get("X-Store-Id") or request.COOKIES.get(settings.STORE_COOKIE)
        m = next((x for x in memberships if str(x.store_id) == str(wanted)), memberships[0])
    if not has_role(m.role, min_role):
        raise forbidden()
    return AdminContext(user=user, store=m.store, role=m.role, memberships=memberships)


def _clean_host(host: str | None) -> str:
    return (host or "").split(":")[0].strip().lower()


def request_host(request) -> str:
    return _clean_host(request.headers.get("X-Store-Host") or request.get_host())


def host_kind(host: str) -> tuple[str, str | None]:
    """("platform" | "panel" | "subdomain" | "other", subdomain)"""
    pd = settings.PLATFORM_DOMAIN
    if pd:
        if host in (pd, f"www.{pd}"):
            return "platform", None
        if host == f"{settings.PANEL_SUBDOMAIN}.{pd}":
            return "panel", None
        if host.endswith(f".{pd}"):
            return "subdomain", host[: -len(pd) - 1]
    return "other", None


def store_for_host(host: str) -> Store | None:
    """The store a host belongs to (custom domain or subdomain), else None."""
    if not host:
        return None
    store = Store.objects.filter(domain=host).first()
    if store:
        return store
    kind, sub = host_kind(host)
    if kind == "subdomain" and sub and "." not in sub and sub not in settings.RESERVED_SUBDOMAINS:
        return Store.objects.filter(slug=sub).first()
    return None


def ensure_active(store: Store) -> Store:
    """A store whose subscription ended is closed to visitors (its panel still works)."""
    sub = getattr(store, "subscription", None)
    if sub is not None and not sub.is_active:
        raise ApiError("این فروشگاه در حال حاضر غیرفعال است", 403, {"reason": "inactive"})
    return store


def resolve_public_store(request) -> Store:
    host = request_host(request)
    store = store_for_host(host)
    if store:
        return ensure_active(store)
    # Hosts under the platform domain (landing, panel, unknown/reserved subdomains)
    # never fall back to another store, whatever the fallback settings say
    if host_kind(host)[0] != "other":
        raise not_found("فروشگاه یافت نشد")
    if settings.PLATFORM_DOMAIN and not settings.DEFAULT_STORE_SLUG:
        # Production: an unknown foreign host must never show another store either
        raise not_found("فروشگاه یافت نشد")
    if settings.DEFAULT_STORE_SLUG:
        store = Store.objects.filter(slug=settings.DEFAULT_STORE_SLUG).first()
        if store:
            return ensure_active(store)
    store = Store.objects.order_by("created_at").first()
    if not store:
        raise not_found("فروشگاهی تعریف نشده است")
    return ensure_active(store)


class StoreRolePermission(BasePermission):
    """
    Resolves request.admin (AdminContext) for the current store.
    View attribute `min_role` (default "editor"); `write_role` for unsafe methods.
    """

    def has_permission(self, request, view):
        role = getattr(view, "min_role", "editor")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            role = getattr(view, "write_role", role)
        request.admin = resolve_admin(request, role)
        return True

"""
Store (tenant) resolution.

Admin requests: the store comes from the `X-Store-Id` header or the `ws_store`
cookie and MUST be one the user is a member of (otherwise the first one).
Public requests: the store comes from the storefront host — `X-Store-Host`
header (sent by the frontend server), else the request Host — matching a
store's custom domain; otherwise DEFAULT_STORE_SLUG or the first store.
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
    wanted = request.headers.get("X-Store-Id") or request.COOKIES.get(settings.STORE_COOKIE)
    m = next((x for x in memberships if str(x.store_id) == str(wanted)), memberships[0])
    if not has_role(m.role, min_role):
        raise forbidden()
    return AdminContext(user=user, store=m.store, role=m.role, memberships=memberships)


def _clean_host(host: str | None) -> str:
    return (host or "").split(":")[0].strip().lower()


def resolve_public_store(request) -> Store:
    host = _clean_host(request.headers.get("X-Store-Host") or request.get_host())
    if host:
        store = Store.objects.filter(domain=host).first()
        if store:
            return store
    if settings.DEFAULT_STORE_SLUG:
        store = Store.objects.filter(slug=settings.DEFAULT_STORE_SLUG).first()
        if store:
            return store
    store = Store.objects.order_by("created_at").first()
    if not store:
        raise not_found("فروشگاهی تعریف نشده است")
    return store


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

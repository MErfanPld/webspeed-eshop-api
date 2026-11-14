from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.core.errors import bad_request, forbidden
from apps.core.views import AdminView, PublicView, body

from . import services
from .tenancy import resolve_public_store


class StoreView(AdminView):
    """GET current store · PATCH settings (admin+) · POST switch or create."""

    write_role = "editor"  # POST switch/create allowed to any member; PATCH checked below

    @extend_schema(summary="Current store, role and memberships", responses={200: dict})
    def get(self, request):
        a = request.admin
        return Response({"store": services.serialize(a.store), "role": a.role, "memberships": a.membership_payload()})

    @extend_schema(summary="Update current store (name, domain, settings) — admin+", request=dict, responses={200: dict})
    def patch(self, request):
        a = request.admin
        if a.role == "editor":
            raise forbidden()
        return Response({"store": services.serialize(services.update_store(a.store, body(request)))})

    @extend_schema(
        summary="Switch store {storeId} or create one {create: {name, slug, domain}}",
        request=dict,
        responses={200: dict, 201: dict},
    )
    def post(self, request):
        a = request.admin
        data = body(request)
        if isinstance(data.get("create"), dict):
            c = data["create"]
            store = services.create_store(a.user, c.get("name"), c.get("slug"), c.get("domain"))
            response = Response({"store": services.serialize(store), "storeId": str(store.id)}, status=201)
        else:
            store_id = data.get("storeId")
            if not store_id:
                raise bad_request("storeId الزامی است")
            if not any(str(m.store_id) == str(store_id) for m in a.memberships):
                raise forbidden("به این فروشگاه دسترسی ندارید")
            response = Response({"ok": True, "storeId": str(store_id)})
        response.set_cookie(
            settings.STORE_COOKIE,
            response.data["storeId"],
            httponly=True,
            secure=settings.JWT_COOKIE_SECURE,
            samesite=settings.JWT_COOKIE_SAMESITE,
            domain=settings.JWT_COOKIE_DOMAIN,
            path="/",
        )
        return response


class StoresListView(AdminView):
    @extend_schema(summary="Stores the user can access", responses={200: dict})
    def get(self, request):
        a = request.admin
        return Response(
            {
                "stores": [
                    {**services.serialize(m.store), "role": m.role, "current": m.store_id == a.store.id}
                    for m in a.memberships
                ]
            }
        )


class PublicStoreView(PublicView):
    @extend_schema(
        summary="Storefront store info (resolved from X-Store-Host / Host)",
        responses={200: dict},
    )
    def get(self, request):
        return Response({"store": services.public_info(resolve_public_store(request))})

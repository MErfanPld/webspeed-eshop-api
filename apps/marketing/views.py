from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.core import ratelimit
from apps.core.authentication import enforce_origin
from apps.core.models import audit
from apps.core.views import AdminView, PublicView, body
from apps.stores.tenancy import resolve_public_store

from . import services as s
from .models import Coupon


class AdminCouponListView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Coupons of the current store", responses={200: dict})
    def get(self, request):
        return Response({"coupons": [s.serialize(c) for c in Coupon.objects.filter(store=request.admin.store)]})

    @extend_schema(summary="Create coupon (admin+)", request=dict, responses={201: dict})
    def post(self, request):
        c = s.save_coupon(request.admin.store, body(request))
        audit(request.admin, "coupon.create", c.code)
        return Response({"coupon": s.serialize(c)}, status=201)


class AdminCouponDetailView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Update coupon (admin+)", request=dict, responses={200: dict})
    def put(self, request, coupon_id):
        c = s.save_coupon(request.admin.store, body(request), coupon_id)
        audit(request.admin, "coupon.update", c.code)
        return Response({"coupon": s.serialize(c)})

    @extend_schema(summary="Delete coupon (admin+)", responses={200: dict})
    def delete(self, request, coupon_id):
        s.delete_coupon(request.admin.store, coupon_id)
        audit(request.admin, "coupon.delete", coupon_id)
        return Response({"ok": True})


class CouponValidateView(PublicView):
    @extend_schema(
        summary="Check a coupon {code, subtotal, phone?} → discount", request=dict, responses={200: dict, 400: dict}
    )
    def post(self, request):
        enforce_origin(request)
        ratelimit.enforce(
            f"coupon:{ratelimit.client_ip(request)}", 20, 600, "تلاش زیاد بود؛ کمی بعد دوباره امتحان کنید."
        )
        d = body(request)
        try:
            subtotal = max(0, int(d.get("subtotal") or 0))
        except (TypeError, ValueError):
            subtotal = 0
        phone = d.get("phone") if isinstance(d.get("phone"), str) else None
        return Response({"coupon": s.preview(resolve_public_store(request), d.get("code"), subtotal, phone)})

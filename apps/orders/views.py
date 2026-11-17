import json

from django.conf import settings
from django.core import signing
from django.http import FileResponse
from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core import ratelimit
from apps.core.authentication import enforce_origin
from apps.core.errors import ApiError, bad_request, not_found
from apps.core.models import audit
from apps.core.pagination import paginate_optional
from apps.core.views import AdminView, PublicView, body
from apps.stores.tenancy import resolve_public_store

from . import payments
from . import services as s
from .models import Order

RECEIPT_SALT = "ws.receipt"


def presigned_receipt_url(name: str) -> str:
    """Presigned GET for the private bucket, signed for the browser-facing endpoint."""
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=settings.S3_BROWSER_ENDPOINT_URL or settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.S3_PRIVATE_BUCKET,
            "Key": name,
            "ResponseCacheControl": "private, no-store",
        },
        ExpiresIn=settings.PRIVATE_URL_EXPIRE_SECONDS,
    )


class CheckoutView(PublicView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        summary="Checkout (multipart: data=JSON{customer, items[{productId,size,color,quantity}]}, receipt=image)",
        description="Prices, shipping and stock are computed server-side; client prices are ignored.",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {"data": {"type": "string"}, "receipt": {"type": "string", "format": "binary"}},
            }
        },
        responses={201: dict, 400: dict, 409: dict, 429: dict},
    )
    def post(self, request):
        enforce_origin(request)
        ratelimit.enforce(
            f"order:{ratelimit.client_ip(request)}", 10, 10 * 60, "تعداد درخواست‌ها زیاد است؛ کمی بعد دوباره تلاش کنید."
        )
        try:
            data = json.loads(request.data.get("data") or "{}")
        except (TypeError, ValueError):
            raise bad_request("درخواست نامعتبر است") from None
        if not isinstance(data, dict):
            raise bad_request("درخواست نامعتبر است")
        store = resolve_public_store(request)
        method = data.get("paymentMethod") or "card"
        order = s.create_order(
            store,
            data.get("customer"),
            data.get("items"),
            request.FILES.get("receipt"),
            payment_method=method,
            coupon_code=data.get("coupon") if isinstance(data.get("coupon"), str) else "",
        )
        out = {"number": order.number, "total": order.total, "discount": order.discount, "status": order.status}
        if order.payment_method == Order.PaymentMethod.ONLINE:
            _payment, url = payments.start(order)
            out["paymentUrl"] = url
        return Response({"order": out}, status=201)


class TrackView(PublicView):
    @extend_schema(
        summary="Track an order (number AND buyer phone required)",
        parameters=[OpenApiParameter("number", str), OpenApiParameter("phone", str)],
        responses={200: dict, 404: dict, 429: dict},
    )
    def get(self, request):
        ratelimit.enforce(
            f"track:{ratelimit.client_ip(request)}", 20, 10 * 60, "تعداد درخواست‌ها زیاد است؛ کمی بعد دوباره تلاش کنید."
        )
        number, phone = request.query_params.get("number", ""), request.query_params.get("phone", "")
        if not number or not phone:
            raise bad_request("شماره سفارش و موبایل را وارد کنید")
        o = s.track(resolve_public_store(request), number, phone)
        if not o:
            raise not_found("سفارشی با این مشخصات یافت نشد")
        return Response(
            {
                "order": {
                    "number": o.number,
                    "status": o.status,
                    "total": o.total,
                    "shipping": o.shipping,
                    "createdAt": s._iso(o.created_at),
                    "items": [{k: i[k] for k in ("name", "quantity", "size", "color", "lineTotal")} for i in o.items],
                }
            }
        )


class AdminOrderListView(AdminView):
    @extend_schema(
        summary="Orders of the current store",
        operation_id="admin_orders_list",
        parameters=[OpenApiParameter(n, str) for n in ("status", "q", "payment", "page", "pageSize")],
        responses={200: dict},
    )
    def get(self, request):
        qp = request.query_params
        qs = s.list_orders(request.admin.store, qp.get("status"), qp.get("q"), qp.get("payment"))
        items, meta = paginate_optional(qs, request, 500)
        out = {"orders": [s.serialize(o) for o in items]}
        if meta:
            out["pagination"] = meta
        return Response(out)


class AdminOrderDetailView(AdminView):
    write_role = "admin"
    parser_classes = [JSONParser]

    @extend_schema(summary="Order detail", responses={200: dict})
    def get(self, request, order_id):
        return Response({"order": s.serialize(s.get_order(request.admin.store, order_id))})

    @extend_schema(summary="Change status {status, note?} (admin+)", request=dict, responses={200: dict})
    def patch(self, request, order_id):
        d = body(request)
        order = s.update_status(request.admin.store, order_id, d.get("status"), d.get("note"))
        audit(request.admin, "order.status", order.number, status=order.status)
        return Response({"order": s.serialize(order)})


class AdminOrderReceiptView(AdminView):
    @extend_schema(summary="Short-lived signed URL for the private payment receipt", responses={200: dict})
    def get(self, request, order_id):
        order = s.get_order(request.admin.store, order_id)
        if not order.receipt:
            raise not_found("رسید یافت نشد")
        ttl = settings.PRIVATE_URL_EXPIRE_SECONDS
        if settings.STORAGE_BACKEND == "s3":
            url = presigned_receipt_url(order.receipt.name)
        else:
            token = signing.dumps({"s": str(order.store_id), "o": str(order.id)}, salt=RECEIPT_SALT)
            url = request.build_absolute_uri(reverse("receipt-file", args=[token]))
        return Response({"url": url, "expiresIn": ttl})


class SignedReceiptFileView(PublicView):
    """Local-storage counterpart of an S3 presigned URL."""

    @extend_schema(exclude=True)
    def get(self, request, token):
        try:
            data = signing.loads(token, salt=RECEIPT_SALT, max_age=settings.PRIVATE_URL_EXPIRE_SECONDS)
        except signing.BadSignature:
            raise ApiError("لینک منقضی یا نامعتبر است", 403) from None
        order = Order.objects.filter(store_id=data["s"], id=data["o"]).first()
        if not order or not order.receipt:
            raise not_found("رسید یافت نشد")
        response = FileResponse(order.receipt.open("rb"))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


class PaymentCallbackView(PublicView):
    """Gateway → API redirect. Verifies once, then sends the buyer to the frontend."""

    @extend_schema(
        summary="Payment gateway callback (Authority, Status=OK|NOK) → redirect to the frontend result page",
        parameters=[OpenApiParameter("Authority", str), OpenApiParameter("Status", str)],
        responses={302: None},
    )
    def get(self, request):
        from django.http import HttpResponseRedirect

        qp = request.query_params
        authority = qp.get("Authority") or qp.get("authority") or ""
        order, ok = payments.verify(authority[:100], qp.get("Status") or qp.get("status") or "")
        if not order:
            return HttpResponseRedirect(f"{settings.FRONTEND_URL}/checkout/result?status=failed")  # unknown payment
        return HttpResponseRedirect(payments.result_url(order, ok))


class MockGatewayView(PublicView):
    """Development-only fake bank page (PAYMENT_PROVIDER=mock)."""

    @extend_schema(exclude=True)
    def get(self, request, authority):
        from django.http import HttpResponse
        from django.utils.html import escape

        from .models import Payment

        if settings.PAYMENT_PROVIDER != "mock":
            raise not_found("یافت نشد")
        p = Payment.objects.select_related("order").filter(authority=authority).first()
        if not p:
            raise not_found("تراکنش یافت نشد")
        cb = payments.callback_url()
        a = escape(authority)
        html = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>درگاه پرداخت آزمایشی</title>
<style>body{{font-family:Tahoma,sans-serif;background:#f1f5f9;display:grid;place-items:center;min-height:100vh;margin:0}}
.c{{background:#fff;padding:32px;border-radius:16px;box-shadow:0 10px 30px #0001;max-width:360px;width:90%;text-align:center}}
a{{display:block;padding:12px;border-radius:10px;margin-top:12px;text-decoration:none;color:#fff;font-weight:bold}}
.ok{{background:#16a34a}}.no{{background:#dc2626}}small{{color:#64748b}}</style></head><body><div class="c">
<h2>درگاه پرداخت آزمایشی</h2><small>بدون پرداخت واقعی — فقط برای تست</small>
<p>سفارش <b>{escape(p.order.number)}</b></p><p>مبلغ: <b>{p.amount:,} تومان</b></p>
<a class="ok" id="pay-ok" href="{cb}?Authority={a}&Status=OK">پرداخت موفق</a>
<a class="no" id="pay-fail" href="{cb}?Authority={a}&Status=NOK">انصراف / پرداخت ناموفق</a>
</div></body></html>"""
        payments._log(f"mock gateway opened for {p.order.number}")
        return HttpResponse(html)

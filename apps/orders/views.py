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
from apps.core.views import AdminView, PublicView, body
from apps.stores.tenancy import resolve_public_store

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
        request={"multipart/form-data": {"type": "object", "properties": {
            "data": {"type": "string"}, "receipt": {"type": "string", "format": "binary"}}}},
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
        order = s.create_order(store, data.get("customer"), data.get("items"), request.FILES.get("receipt"))
        return Response({"order": {"number": order.number, "total": order.total, "status": order.status}}, status=201)


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
                    "items": [
                        {k: i[k] for k in ("name", "quantity", "size", "color", "lineTotal")} for i in o.items
                    ],
                }
            }
        )


class AdminOrderListView(AdminView):
    @extend_schema(
        summary="Orders of the current store", operation_id="admin_orders_list",
        parameters=[OpenApiParameter("status", str), OpenApiParameter("q", str)],
        responses={200: dict},
    )
    def get(self, request):
        qs = s.list_orders(request.admin.store, request.query_params.get("status"), request.query_params.get("q"))
        return Response({"orders": [s.serialize(o) for o in qs[:500]]})


class AdminOrderDetailView(AdminView):
    write_role = "admin"
    parser_classes = [JSONParser]

    @extend_schema(summary="Order detail", responses={200: dict})
    def get(self, request, order_id):
        return Response({"order": s.serialize(s.get_order(request.admin.store, order_id))})

    @extend_schema(summary="Change status {status, note?} (admin+)", request=dict, responses={200: dict})
    def patch(self, request, order_id):
        d = body(request)
        return Response({"order": s.serialize(s.update_status(request.admin.store, order_id, d.get("status"), d.get("note")))})


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

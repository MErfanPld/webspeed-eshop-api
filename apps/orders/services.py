"""
Order rules (ported from frontend src/server/services/orders.ts).

- Prices, shipping and totals are computed on the server from the catalog.
- Stock is reserved atomically (row locks); cancelling restores it and
  re-opening a cancelled order reserves it again.
- Receipts live in private storage and are only reachable via signed URLs.
"""
import re
import secrets
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.errors import ApiError, bad_request, conflict, not_found
from apps.core.validators import to_english_digits
from apps.customers.models import Customer
from apps.media.services import read_upload
from apps.stores.models import Store

from .models import Order

STATUSES = [c.value for c in Order.Status]
PHONE_RE = re.compile(r"^09\d{9}$")
POSTAL_RE = re.compile(r"^\d{10}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def _text(v, max_len) -> str:
    return v.strip()[:max_len] if isinstance(v, str) else ""


def normalize_phone(v: str) -> str:
    return re.sub(r"[\s-]", "", to_english_digits(v or ""))


def validate_customer(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    c = {
        "fullName": _text(raw.get("fullName"), 120),
        "phone": normalize_phone(_text(raw.get("phone"), 20)),
        "province": _text(raw.get("province"), 60),
        "city": _text(raw.get("city"), 60),
        "address": _text(raw.get("address"), 500),
        "postalCode": normalize_phone(_text(raw.get("postalCode"), 20)),
    }
    email = _text(raw.get("email"), 200)
    if email:
        c["email"] = email
    errors = {}
    if not c["fullName"]:
        errors["fullName"] = "نام الزامی است"
    if not PHONE_RE.match(c["phone"]):
        errors["phone"] = "شماره موبایل معتبر نیست (مثال: 09121234567)"
    if email and not EMAIL_RE.match(email):
        errors["email"] = "ایمیل معتبر نیست"
    if not c["province"]:
        errors["province"] = "استان الزامی است"
    if not c["city"]:
        errors["city"] = "شهر الزامی است"
    if not c["address"]:
        errors["address"] = "آدرس الزامی است"
    if not POSTAL_RE.match(c["postalCode"]):
        errors["postalCode"] = "کد پستی باید ۱۰ رقم باشد"
    if errors:
        raise bad_request("اطلاعات ارسال را بررسی کنید", errors)
    return c


def serialize(o: Order, admin: bool = True) -> dict:
    return {
        "id": str(o.id),
        "number": o.number,
        "status": o.status,
        "customer": o.customer_info,
        "items": o.items,
        "subtotal": o.subtotal,
        "shipping": o.shipping,
        "total": o.total,
        "hasReceipt": bool(o.receipt),
        "note": o.note or None,
        "createdAt": _iso(o.created_at),
        "updatedAt": _iso(o.updated_at),
    }


def _merge_items(raw_items) -> list[dict]:
    if not isinstance(raw_items, list) or not raw_items:
        raise bad_request("سبد خرید خالی است")
    if len(raw_items) > 50:
        raise bad_request("تعداد اقلام سبد بیش از حد مجاز است")
    merged: dict[tuple, dict] = {}
    for raw in raw_items:
        raw = raw if isinstance(raw, dict) else {}
        pid, size, color = _text(raw.get("productId"), 80), _text(raw.get("size"), 40), _text(raw.get("color"), 40)
        try:
            qty = int(raw.get("quantity"))
        except (TypeError, ValueError):
            qty = 0
        if not pid or qty < 1 or qty > 20:
            raise bad_request("اقلام سبد خرید نامعتبر است")
        key = (pid, size, color)
        merged.setdefault(key, {"productId": pid, "size": size, "color": color, "quantity": 0})
        merged[key]["quantity"] += qty
    return list(merged.values())


def _new_number() -> str:
    d = timezone.now()
    return f"WS-{d:%y%m%d}-{secrets.randbelow(9000) + 1000}{secrets.randbelow(90) + 10}"


def _reserve(store: Store, lines: list[tuple[str, int]]):
    """Lock product rows and decrement stock; raise on insufficient stock."""
    keys = sorted({k for k, _ in lines})
    products = {p.key: p for p in Product.objects.select_for_update().filter(store=store, key__in=keys).order_by("key")}
    need: dict[str, int] = {}
    for k, q in lines:
        need[k] = need.get(k, 0) + q
    for k, q in need.items():
        p = products.get(k)
        if not p or p.status != Product.Status.ACTIVE:
            raise bad_request("یکی از محصولات سبد دیگر موجود نیست")
        if p.stock < q:
            raise conflict(f"موجودی «{p.name}» کافی نیست (موجودی: {p.stock})")
    for k, q in need.items():
        p = products[k]
        p.stock -= q
        p.save(update_fields=["stock", "updated_at"])


def _restore(store: Store, lines: list[tuple[str, int]]):
    keys = sorted({k for k, _ in lines})
    products = {p.key: p for p in Product.objects.select_for_update().filter(store=store, key__in=keys).order_by("key")}
    for k, q in lines:
        p = products.get(k)
        if p:
            p.stock += q
            p.save(update_fields=["stock", "updated_at"])


def create_order(store: Store, customer_raw, items_raw, receipt_file) -> Order:
    customer = validate_customer(customer_raw)
    requested = _merge_items(items_raw)

    # Card-to-card payments need a receipt image (validated before any DB work)
    if receipt_file is None:
        raise bad_request("تصویر رسید پرداخت را آپلود کنید")
    try:
        receipt_bytes, _mime, ext = read_upload(receipt_file, "رسید")
    except ApiError as e:
        if e.status_code == 400:
            raise bad_request("رسید باید تصویر PNG، JPG، WEBP یا GIF باشد") from None
        raise

    settings_ = store.settings or {}
    shipping_conf = settings_.get("shipping") or {}

    with transaction.atomic():
        products = {
            p.key: p
            for p in Product.objects.select_related("category").filter(
                store=store, key__in=[r["productId"] for r in requested]
            )
        }
        items = []
        for r in requested:
            p = products.get(r["productId"])
            if not p or p.status != Product.Status.ACTIVE:
                raise bad_request("یکی از محصولات سبد دیگر موجود نیست")
            sizes = (p.variants or {}).get("sizes") or []
            colors = (p.variants or {}).get("colors") or []
            if sizes and r["size"] not in sizes:
                raise bad_request(f"سایز انتخابی برای «{p.name}» معتبر نیست")
            if colors and not any(c.get("name") == r["color"] for c in colors):
                raise bad_request(f"رنگ انتخابی برای «{p.name}» معتبر نیست")
            items.append(
                {
                    "productId": p.key,
                    "slug": p.slug,
                    "name": p.name,
                    "image": (p.images or [""])[0],
                    "size": r["size"],
                    "color": r["color"],
                    "unitPrice": p.price,
                    "quantity": r["quantity"],
                    "lineTotal": p.price * r["quantity"],
                }
            )

        subtotal = sum(i["lineTotal"] for i in items)
        flat = max(0, int(shipping_conf.get("flatRate") or 0))
        free_over = int(shipping_conf.get("freeOver") or 0)
        shipping = 0 if free_over > 0 and subtotal >= free_over else flat

        _reserve(store, [(i["productId"], i["quantity"]) for i in items])

        cust, _ = Customer.objects.get_or_create(
            store=store, phone=customer["phone"], defaults={"name": customer["fullName"], "email": customer.get("email", "")}
        )
        if cust.name != customer["fullName"] or (customer.get("email") and cust.email != customer["email"]):
            cust.name = customer["fullName"]
            cust.email = customer.get("email", cust.email)
            cust.save()

        order = Order(
            store=store,
            customer=cust,
            customer_info=customer,
            items=items,
            subtotal=subtotal,
            shipping=shipping,
            total=subtotal + shipping,
        )
        for _ in range(5):
            order.number = _new_number()
            if not Order.objects.filter(store=store, number=order.number).exists():
                break
        order.receipt.save(f"receipt.{ext}", ContentFile(receipt_bytes), save=False)
        try:
            with transaction.atomic():
                order.save()
        except IntegrityError:
            order.receipt.delete(save=False)
            raise
    return order


def get_order(store: Store, order_id) -> Order:
    o = Order.objects.filter(store=store, id=order_id).first()
    if not o:
        raise not_found("سفارش یافت نشد")
    return o


def list_orders(store: Store, status: str | None = None, q: str | None = None):
    qs = Order.objects.filter(store=store)
    if status in STATUSES:
        qs = qs.filter(status=status)
    if q:
        q = q.strip()[:60]
        qs = qs.filter(
            Q(number__icontains=q) | Q(customer_info__fullName__icontains=q) | Q(customer_info__phone__icontains=q)
        )
    return qs.order_by("-created_at")


@transaction.atomic
def update_status(store: Store, order_id, status, note=None) -> Order:
    if status not in STATUSES:
        raise bad_request("وضعیت نامعتبر است")
    order = Order.objects.select_for_update().filter(store=store, id=order_id).first()
    if not order:
        raise not_found("سفارش یافت نشد")
    lines = [(i["productId"], int(i["quantity"])) for i in order.items]
    if order.status != Order.Status.CANCELLED and status == Order.Status.CANCELLED:
        _restore(store, lines)
    elif order.status == Order.Status.CANCELLED and status != Order.Status.CANCELLED:
        _reserve(store, lines)
    order.status = status
    if isinstance(note, str):
        order.note = note[:1000]
    order.save()
    return order


def track(store: Store, number: str, phone: str) -> Order | None:
    o = Order.objects.filter(store=store, number=(number or "").strip().upper()).first()
    if not o or o.customer_info.get("phone") != normalize_phone(phone):
        return None
    return o


def stats(store: Store, days: int = 30) -> dict:
    since = timezone.now() - timedelta(days=days)
    base = Order.objects.filter(store=store, created_at__gte=since)
    paid = base.exclude(status=Order.Status.CANCELLED)
    agg = paid.aggregate(orders=Count("id"), revenue=Sum("total"))
    orders, revenue = agg["orders"] or 0, agg["revenue"] or 0
    by_day = (
        paid.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total"), orders=Count("id"))
        .order_by("day")
    )
    low = Product.objects.filter(store=store, status=Product.Status.ACTIVE, stock__lte=3).order_by("stock")[:10]
    return {
        "days": days,
        "orders": orders,
        "revenue": revenue,
        "avgOrder": round(revenue / orders) if orders else 0,
        "customers": base.values("customer_info__phone").distinct().count(),
        "pending": Order.objects.filter(store=store, status=Order.Status.PENDING).count(),
        "byDay": [{"day": d["day"].isoformat(), "revenue": d["revenue"], "orders": d["orders"]} for d in by_day],
        "lowStock": [{"id": p.key, "name": p.name, "stock": p.stock} for p in low],
        "recent": [serialize(o) for o in Order.objects.filter(store=store).order_by("-created_at")[:5]],
    }

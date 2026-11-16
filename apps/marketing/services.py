"""
Discount coupons.

- Validation and the discount amount are always computed on the server.
- `redeem()` runs inside the checkout transaction and locks the coupon row,
  so concurrent orders can't exceed `usage_limit`.
"""

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.errors import bad_request, conflict, not_found
from apps.stores.models import Store

from .models import Coupon, CouponRedemption


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def normalize_code(v) -> str:
    return v.strip().upper()[:40] if isinstance(v, str) else ""


def serialize(c: Coupon) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "kind": c.kind,
        "value": c.value,
        "maxDiscount": c.max_discount,
        "minOrder": c.min_order,
        "usageLimit": c.usage_limit,
        "perCustomerLimit": c.per_customer_limit,
        "usedCount": c.used_count,
        "startsAt": _iso(c.starts_at),
        "endsAt": _iso(c.ends_at),
        "active": c.active,
        "createdAt": _iso(c.created_at),
    }


def _opt_int(v, field, errors, minimum=1):
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        errors[field] = "عدد معتبر وارد کنید"
        return None
    if n < minimum:
        errors[field] = "مقدار نامعتبر است"
    return n


def _opt_dt(v, field, errors):
    if v in (None, ""):
        return None
    dt = parse_datetime(v) if isinstance(v, str) else None
    if not dt:
        errors[field] = "تاریخ نامعتبر است"
    elif timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


@transaction.atomic
def save_coupon(store: Store, data: dict, coupon_id: int | None = None) -> Coupon:
    errors = {}
    code = normalize_code(data.get("code"))
    if not code or not code.replace("-", "").replace("_", "").isalnum():
        errors["code"] = "کد تخفیف فقط حروف انگلیسی، عدد و - باشد"
    kind = data.get("kind")
    if kind not in Coupon.Kind.values:
        errors["kind"] = "نوع تخفیف نامعتبر است"
    value = _opt_int(data.get("value"), "value", errors)
    if value is None and "value" not in errors:
        errors["value"] = "مقدار تخفیف الزامی است"
    if kind == "percent" and value and value > 100:
        errors["value"] = "درصد باید بین ۱ تا ۱۰۰ باشد"
    values = {
        "code": code,
        "kind": kind,
        "value": value,
        "max_discount": _opt_int(data.get("maxDiscount"), "maxDiscount", errors),
        "min_order": _opt_int(data.get("minOrder"), "minOrder", errors, 0) or 0,
        "usage_limit": _opt_int(data.get("usageLimit"), "usageLimit", errors),
        "per_customer_limit": _opt_int(data.get("perCustomerLimit"), "perCustomerLimit", errors),
        "starts_at": _opt_dt(data.get("startsAt"), "startsAt", errors),
        "ends_at": _opt_dt(data.get("endsAt"), "endsAt", errors),
        "active": data.get("active", True) is not False,
    }
    if values["starts_at"] and values["ends_at"] and values["ends_at"] <= values["starts_at"]:
        errors["endsAt"] = "تاریخ پایان باید بعد از شروع باشد"
    if errors:
        raise bad_request("اطلاعات کد تخفیف را بررسی کنید", errors)
    if coupon_id:
        c = Coupon.objects.select_for_update().filter(store=store, id=coupon_id).first()
        if not c:
            raise not_found("کد تخفیف یافت نشد")
    else:
        c = Coupon(store=store)
    if Coupon.objects.filter(store=store, code=code).exclude(pk=c.pk).exists():
        raise conflict("این کد تخفیف قبلاً ساخته شده")
    for k, v in values.items():
        setattr(c, k, v)
    c.save()
    return c


def delete_coupon(store: Store, coupon_id: int):
    deleted, _ = Coupon.objects.filter(store=store, id=coupon_id).delete()
    if not deleted:
        raise not_found("کد تخفیف یافت نشد")


def _check(c: Coupon | None, subtotal: int, phone: str | None) -> int:
    """Return the discount amount or raise a Persian 400."""
    now = timezone.now()
    if not c or not c.active:
        raise bad_request("کد تخفیف معتبر نیست", {"coupon": "کد تخفیف معتبر نیست"})
    if c.starts_at and now < c.starts_at:
        raise bad_request("این کد تخفیف هنوز فعال نشده", {"coupon": "هنوز فعال نشده"})
    if c.ends_at and now >= c.ends_at:
        raise bad_request("مهلت استفاده از این کد تمام شده", {"coupon": "منقضی شده"})
    if c.usage_limit is not None and c.used_count >= c.usage_limit:
        raise bad_request("ظرفیت استفاده از این کد تمام شده", {"coupon": "ظرفیت تمام شده"})
    if subtotal < c.min_order:
        raise bad_request(
            f"حداقل مبلغ سفارش برای این کد {c.min_order:,} تومان است", {"coupon": "حداقل مبلغ رعایت نشده"}
        )
    if phone and c.per_customer_limit is not None:
        used = CouponRedemption.objects.filter(coupon=c, phone=phone).count()
        if used >= c.per_customer_limit:
            raise bad_request("سقف استفاده شما از این کد پر شده", {"coupon": "قبلاً استفاده کرده‌اید"})
    if c.kind == Coupon.Kind.PERCENT:
        amount = subtotal * c.value // 100
        if c.max_discount:
            amount = min(amount, c.max_discount)
    else:
        amount = c.value
    return max(0, min(amount, subtotal))


def preview(store: Store, code: str, subtotal: int, phone: str | None = None) -> dict:
    c = Coupon.objects.filter(store=store, code=normalize_code(code)).first()
    amount = _check(c, subtotal, phone)
    return {"code": c.code, "discount": amount, "kind": c.kind, "value": c.value}


def redeem(store: Store, code: str, subtotal: int, phone: str) -> tuple[Coupon, int]:
    """Lock, validate and count a use. Must run inside the order transaction."""
    c = Coupon.objects.select_for_update().filter(store=store, code=normalize_code(code)).first()
    amount = _check(c, subtotal, phone)
    Coupon.objects.filter(pk=c.pk).update(used_count=F("used_count") + 1)
    return c, amount


def release(order) -> None:
    """Give the use back when an order is cancelled (idempotent)."""
    r = CouponRedemption.objects.filter(order=order).select_related("coupon").first()
    if r:
        Coupon.objects.filter(pk=r.coupon_id, used_count__gt=0).update(used_count=F("used_count") - 1)
        r.delete()

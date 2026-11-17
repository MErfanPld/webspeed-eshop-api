"""
Online payment gateways (settings.PAYMENT_PROVIDER).

- "mock"      development: no real money. The "gateway" is a local page served
              by this API (/api/v1/payments/mock/<authority>) and every step is
              printed to the terminal.
- "zarinpal"  https://www.zarinpal.com (ZARINPAL_MERCHANT_ID, ZARINPAL_SANDBOX).

Flow: checkout creates the order (status pending, unpaid) and a Payment →
browser is sent to the gateway → gateway redirects to
/api/v1/payments/callback?authority=…&Status=OK|NOK → verify (idempotent) →
redirect to FRONTEND_URL/checkout/result. A failed payment cancels the order
and restores stock.
"""

import json
import logging
import secrets
import urllib.request

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.errors import ApiError

from .models import Order, Payment

logger = logging.getLogger("webspeed.payments")


def _log(msg: str):
    print(f"\n[PAYMENT] {msg}\n", flush=True)  # noqa: T201
    logger.info(msg)


def store_base_url(store) -> str:
    """The shop's own address (subdomain / custom domain), else FRONTEND_URL."""
    from apps.platform.services import store_urls

    return store_urls(store)["url"] or settings.FRONTEND_URL


def callback_url() -> str:
    return f"{settings.API_PUBLIC_URL}/api/v1/payments/callback"


def result_url(order: Order, ok: bool) -> str:
    from urllib.parse import urlencode

    return f"{store_base_url(order.store)}/checkout/result?" + urlencode(
        {"order": order.number, "status": "ok" if ok else "failed"}
    )


# --- Zarinpal (REST v4) -------------------------------------------------------
def _zp_base() -> str:
    return "https://sandbox.zarinpal.com" if settings.ZARINPAL_SANDBOX else "https://payment.zarinpal.com"


def _zp_post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        _zp_base() + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310 (fixed https host)
            return json.loads(res.read().decode() or "{}")
    except Exception as e:
        logger.warning("zarinpal error %s", type(e).__name__)
        raise ApiError("درگاه پرداخت در دسترس نیست؛ کمی بعد دوباره تلاش کنید", 503) from None


# --- Public API ----------------------------------------------------------------
def start(order: Order) -> tuple[Payment, str]:
    """Create a payment for the order and return (payment, gateway URL)."""
    provider = settings.PAYMENT_PROVIDER
    amount = order.total
    if provider == "mock":
        authority = "MOCK-" + secrets.token_hex(12)
        payment = Payment.objects.create(
            store=order.store, order=order, provider="mock", authority=authority, amount=amount
        )
        url = f"{settings.API_PUBLIC_URL}/api/v1/payments/mock/{authority}"
        _log(f"order {order.number}: {amount:,} Toman → mock gateway {url}")
        return payment, url
    if provider == "zarinpal":
        if not settings.ZARINPAL_MERCHANT_ID:
            raise ApiError("درگاه پرداخت پیکربندی نشده است", 503)
        res = _zp_post(
            "/pg/v4/payment/request.json",
            {
                "merchant_id": settings.ZARINPAL_MERCHANT_ID,
                "amount": amount * 10,  # Rial
                "callback_url": callback_url(),
                "description": f"سفارش {order.number}",
                "metadata": {"mobile": order.customer_info.get("phone", "")},
            },
        )
        data = res.get("data") or {}
        if data.get("code") != 100 or not data.get("authority"):
            raise ApiError("ایجاد تراکنش ناموفق بود", 502)
        payment = Payment.objects.create(
            store=order.store, order=order, provider="zarinpal", authority=data["authority"], amount=amount
        )
        return payment, f"{_zp_base()}/pg/StartPay/{data['authority']}"
    raise ApiError("درگاه پرداخت پیکربندی نشده است", 503)


def _verify_with_gateway(payment: Payment, status_param: str) -> tuple[bool, str, dict]:
    if status_param != "OK":
        return False, "", {"status": status_param}
    if payment.provider == "mock":
        return True, f"MOCKREF{secrets.randbelow(10**8):08d}", {"mock": True}
    res = _zp_post(
        "/pg/v4/payment/verify.json",
        {"merchant_id": settings.ZARINPAL_MERCHANT_ID, "amount": payment.amount * 10, "authority": payment.authority},
    )
    data = res.get("data") or {}
    ok = data.get("code") in (100, 101)
    return ok, str(data.get("ref_id") or ""), {"code": data.get("code")}


def verify(authority: str, status_param: str) -> tuple[Order | None, bool]:
    """Verify a gateway callback once; repeated callbacks return the stored result."""
    from apps.marketing.services import release

    from .services import _restore
    from .tasks import notify_order_status

    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("order").filter(authority=authority).first()
        if not payment:
            return None, False
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        if payment.status != Payment.Status.PENDING:
            return order, payment.status == Payment.Status.PAID
        ok, ref_id, raw = _verify_with_gateway(payment, status_param)
        payment.status = Payment.Status.PAID if ok else Payment.Status.FAILED
        payment.ref_id, payment.raw = ref_id, raw
        payment.save()
        if ok:
            order.paid_at = timezone.now()
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["paid_at", "status", "updated_at"])
            _log(f"order {order.number}: PAID ref={ref_id}")
        elif order.status != Order.Status.CANCELLED:
            _restore(order.store, [(i["productId"], int(i["quantity"])) for i in order.items])
            release(order)
            order.status = Order.Status.CANCELLED
            order.note = "پرداخت آنلاین ناموفق بود"
            order.save(update_fields=["status", "note", "updated_at"])
            _log(f"order {order.number}: payment FAILED → cancelled, stock restored")
        transaction.on_commit(lambda: notify_order_status.delay(str(order.id)))
    return order, ok

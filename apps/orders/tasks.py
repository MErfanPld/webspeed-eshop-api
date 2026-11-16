"""Background jobs (Celery). Run eagerly in development (CELERY_TASK_ALWAYS_EAGER)."""

import logging

from celery import shared_task

from apps.core import notify

logger = logging.getLogger(__name__)

STATUS_TEXT = {
    "pending": "ثبت شد و در انتظار بررسی است",
    "confirmed": "تأیید شد",
    "shipped": "ارسال شد",
    "delivered": "تحویل داده شد",
    "cancelled": "لغو شد",
}


@shared_task(bind=True, max_retries=3, ignore_result=True)
def notify_order_status(self, order_id: str):
    from .models import Order

    order = Order.objects.select_related("store").filter(id=order_id).first()
    if not order:
        return
    phone = (order.customer_info or {}).get("phone")
    if not phone:
        return
    text = f"{order.store.name}: سفارش {order.number} {STATUS_TEXT.get(order.status, order.status)}."
    try:
        notify.send_sms(phone, text)
    except notify.NotificationError as e:
        logger.warning("order sms failed: %s", e)
        raise self.retry(exc=e) from None

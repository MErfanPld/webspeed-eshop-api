from django.db import models
from django.db.models import Q

from apps.stores.models import Store


class Coupon(models.Model):  # noqa: DJ008
    class Kind(models.TextChoices):
        PERCENT = "percent"
        FIXED = "fixed"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="coupons")
    code = models.CharField(max_length=40)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    value = models.PositiveIntegerField()  # percent 1–100 or amount in Toman
    max_discount = models.PositiveBigIntegerField(null=True, blank=True)  # cap for percent coupons
    min_order = models.PositiveBigIntegerField(default=0)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)  # total uses
    per_customer_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_coupon_code_per_store"),
            models.CheckConstraint(condition=Q(value__gt=0), name="coupon_value_positive"),
        ]


class CouponRedemption(models.Model):  # noqa: DJ008
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="coupon_redemption")
    phone = models.CharField(max_length=11)
    amount = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["coupon", "phone"])]

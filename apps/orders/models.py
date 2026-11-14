import uuid

from django.core.files.storage import storages
from django.db import models
from django.db.models import Q

from apps.customers.models import Customer
from apps.stores.models import Store


def private_storage():
    return storages["private"]


def receipt_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1]
    return f"stores/{instance.store_id}/receipts/{instance.id}.{ext}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        CONFIRMED = "confirmed"
        SHIPPED = "shipped"
        DELIVERED = "delivered"
        CANCELLED = "cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="orders")
    number = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    # Snapshot of the shipping details at checkout time
    customer_info = models.JSONField()
    # Snapshot of purchased lines (productId, slug, name, image, size, color, unitPrice, quantity, lineTotal)
    items = models.JSONField()
    subtotal = models.BigIntegerField()
    shipping = models.BigIntegerField(default=0)
    total = models.BigIntegerField()
    # Card-to-card payment receipt: private storage, served via signed URLs
    receipt = models.FileField(upload_to=receipt_path, storage=private_storage, max_length=255, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "number"], name="uniq_order_number_per_store"),
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_non_negative"),
        ]
        indexes = [
            models.Index(fields=["store", "-created_at"]),
            models.Index(fields=["store", "status"]),
        ]

    def __str__(self):
        return self.number

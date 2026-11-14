from django.db import models

from apps.stores.models import Store


class Customer(models.Model):
    """A buyer, identified per store by mobile number (created at checkout)."""

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="customers")
    phone = models.CharField(max_length=11)
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["store", "phone"], name="uniq_customer_phone_per_store")]

    def __str__(self):
        return f"{self.name} ({self.phone})"

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


class Address(models.Model):  # noqa: DJ008
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    title = models.CharField(max_length=60, blank=True)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=11)
    province = models.CharField(max_length=60)
    city = models.CharField(max_length=60)
    address = models.CharField(max_length=500)
    postal_code = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]


class ContactMessage(models.Model):  # noqa: DJ008
    """Message sent from the storefront «تماس با ما» page."""

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="contact_messages")
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    message = models.TextField()
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "read", "-created_at"])]


class NewsletterSubscriber(models.Model):  # noqa: DJ008
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="newsletter_subscribers")
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["store", "email"], name="uniq_newsletter_email_per_store")]

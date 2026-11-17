from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """A subscription plan shown on the landing page."""

    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    tagline = models.CharField(max_length=160, blank=True)
    price_monthly = models.PositiveBigIntegerField(default=0)  # Toman
    price_yearly = models.PositiveBigIntegerField(default=0)  # Toman
    features = models.JSONField(default=list, blank=True)  # ["..."] shown as a checklist
    max_products = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    max_members = models.PositiveIntegerField(null=True, blank=True)
    custom_domain = models.BooleanField(default=False)
    highlighted = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    sort = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort", "price_monthly"]

    def __str__(self):
        return self.name


class Subscription(models.Model):
    """A store's plan. Trial first; the platform admin extends `paid_until`."""

    class Status(models.TextChoices):
        TRIAL = "trial", "دوره آزمایشی"
        ACTIVE = "active", "فعال"
        SUSPENDED = "suspended", "معلق"

    store = models.OneToOneField("stores.Store", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    paid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.store} · {self.plan}"

    @property
    def ends_at(self):
        return self.paid_until if self.status == self.Status.ACTIVE else self.trial_ends_at

    @property
    def is_active(self) -> bool:
        if self.status == self.Status.SUSPENDED:
            return False
        end = self.ends_at
        return end is None or end >= timezone.now()

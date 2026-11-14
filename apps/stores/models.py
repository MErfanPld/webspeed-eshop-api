import uuid

from django.conf import settings
from django.db import models


class Store(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=40, unique=True)
    # Custom domain (lowercase, without port); unique when set
    domain = models.CharField(max_length=253, unique=True, null=True, blank=True)
    # tagline, phone, email, address, currency, payment{}, shipping{}
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name


class StoreMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "مالک"
        ADMIN = "admin", "مدیر"
        EDITOR = "editor", "ویرایشگر"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["store", "user"], name="uniq_store_member")]
        indexes = [models.Index(fields=["user", "store"])]

    def __str__(self):
        return f"{self.user} @ {self.store} ({self.role})"


ROLE_RANK = {"editor": 1, "admin": 2, "owner": 3}


def has_role(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]

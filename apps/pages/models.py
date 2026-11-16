from django.db import models

from apps.stores.models import Store


class Page(models.Model):
    """
    A builder page. `key` is the frontend page id ("home", "site-header",
    "page-…"), unique per store. `doc` holds the editable draft (name,
    description, seo, blocks, schemaVersion); `published_blocks` is the last
    published snapshot served to the storefront.
    """

    class Type(models.TextChoices):
        HOME = "home"
        LANDING = "landing"
        CONTENT = "content"
        CUSTOM = "custom"
        HEADER = "header"
        FOOTER = "footer"

    class Status(models.TextChoices):
        DRAFT = "draft"
        PUBLISHED = "published"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="pages")
    key = models.CharField(max_length=120)
    slug = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    doc = models.JSONField(default=dict)
    published_blocks = models.JSONField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "key"], name="uniq_page_key_per_store"),
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_page_slug_per_store"),
        ]
        indexes = [models.Index(fields=["store", "status", "slug"])]

    def __str__(self):
        return f"{self.store_id}:{self.key}"


class SavedBlock(models.Model):  # noqa: DJ008
    """Reusable block group ("block") or full page template ("template")."""

    class Kind(models.TextChoices):
        BLOCK = "block"
        TEMPLATE = "template"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="saved_blocks")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    blocks = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "kind"])]

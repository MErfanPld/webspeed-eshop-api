import uuid

from django.db import models

from apps.stores.models import Store


def media_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1]
    return f"stores/{instance.store_id}/media/{instance.id}.{ext}"


class MediaFile(models.Model):
    """Public store media (product images, banners). Served from the public bucket."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="media")
    name = models.CharField(max_length=120)
    mime = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    file = models.FileField(upload_to=media_path, max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "-created_at"])]

    def __str__(self):
        return self.name

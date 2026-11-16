from django.conf import settings
from django.db import models


class AuditLog(models.Model):  # noqa: DJ008
    """Sensitive admin actions (who did what, when) per store."""

    store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, related_name="audit_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=200, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "-created_at"])]


def audit(admin, action: str, target: str = "", **meta) -> None:
    """Record an action for the admin's current store (never raises)."""
    try:
        AuditLog.objects.create(store=admin.store, user=admin.user, action=action, target=str(target)[:200], meta=meta)
    except Exception:  # auditing must not break the request
        import logging

        logging.getLogger(__name__).exception("audit log failed")

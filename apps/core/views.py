from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.tenancy import StoreRolePermission


class PublicView(APIView):
    """Unauthenticated storefront endpoint (cookie auth ignored, no CSRF)."""

    authentication_classes = []
    permission_classes = [AllowAny]


class AdminView(APIView):
    """Store-scoped admin endpoint. Sets request.admin (AdminContext)."""

    permission_classes = [StoreRolePermission]
    min_role = "editor"


def body(request) -> dict:
    data = request.data
    if hasattr(data, "dict"):
        data = data.dict()
    return data if isinstance(data, dict) else {}


class HealthView(PublicView):
    @extend_schema(summary="Health check", responses={200: dict, 503: dict})
    def get(self, request):
        try:
            with connection.cursor() as c:
                c.execute("SELECT 1")
            return Response({"status": "ok", "database": "ok"})
        except Exception:
            return Response({"status": "error", "database": "unavailable"}, status=503)

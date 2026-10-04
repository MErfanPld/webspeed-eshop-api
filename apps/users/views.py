from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema


class HealthCheckView(APIView):
    """
    Health check endpoint.
    Returns status of the service and optionally database connectivity.
    """

    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Health Check",
        description="Returns the health status of the API and database connection.",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "ok"},
                    "database": {"type": "string", "example": "ok"},
                },
            },
            503: {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "error"},
                    "database": {"type": "string", "example": "unavailable"},
                },
            },
        },
        tags=["Health"],
    )
    def get(self, request):
        db_status = "ok"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_status = "unavailable"

        response_data = {
            "status": "ok" if db_status == "ok" else "error",
            "database": db_status,
        }

        http_status = (
            status.HTTP_200_OK
            if db_status == "ok"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(response_data, status=http_status)

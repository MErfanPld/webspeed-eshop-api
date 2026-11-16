from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.core.views import AdminView

from . import services as s
from .models import MediaFile


class MediaListView(AdminView):
    parser_classes = [MultiPartParser]

    @extend_schema(summary="Media library of the current store", responses={200: dict})
    def get(self, request):
        from apps.core.pagination import paginate_optional

        items, meta = paginate_optional(MediaFile.objects.filter(store=request.admin.store), request, 5000, 40)
        out = {"items": [s.serialize(m) for m in items]}
        if meta:
            out["pagination"] = meta
        return Response(out)

    @extend_schema(
        summary="Upload image (multipart `file`; PNG/JPG/WEBP/GIF ≤ 5MB, checked by magic bytes)",
        request={
            "multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}
        },
        responses={201: dict, 400: dict, 413: dict},
    )
    def post(self, request):
        return Response({"item": s.serialize(s.upload(request.admin.store, request.FILES.get("file")))}, status=201)


class MediaDetailView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Delete media (admin+)", responses={200: dict})
    def delete(self, request, media_id):
        s.delete(request.admin.store, media_id)
        return Response({"ok": True})

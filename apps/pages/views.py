"""
Mirrors the Next.js API used by the builder's HttpPageRepository:
  GET/POST        /admin/pages
  GET/PUT/DELETE  /admin/pages/<id>
  POST            /admin/pages/<id>/{publish,unpublish,duplicate}
  GET             /pages?id=… | ?slug=…   (public, published only)
"""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response

from apps.core.errors import bad_request, not_found
from apps.core.views import AdminView, PublicView, body
from apps.stores.tenancy import resolve_public_store

from . import services as s


class PageListView(AdminView):
    @extend_schema(summary="List pages of the current store", operation_id="admin_pages_list", responses={200: dict})
    def get(self, request):
        return Response({"pages": [s.serialize(p) for p in s.list_pages(request.admin.store)]})

    @extend_schema(summary="Create a page {name, slug, type?}", request=dict, responses={201: dict})
    def post(self, request):
        d = body(request)
        page = s.create_page(request.admin.store, d.get("name"), d.get("slug"), d.get("type"))
        return Response({"page": s.serialize(page)}, status=201)


class PageDetailView(AdminView):
    write_role = "editor"

    @extend_schema(summary="Get a page (draft + published snapshot)", responses={200: dict, 404: dict})
    def get(self, request, key):
        return Response({"page": s.serialize(s.get_page(request.admin.store, key))})

    @extend_schema(summary="Save draft {page: ManagedPage}", request=dict, responses={200: dict})
    def put(self, request, key):
        page = body(request).get("page")
        if not isinstance(page, dict):
            raise bad_request("شناسه صفحه با آدرس مطابقت ندارد")
        return Response({"page": s.serialize(s.save_page(request.admin.store, key, page))})

    @extend_schema(summary="Delete a page (admin+)", responses={200: dict})
    def delete(self, request, key):
        from apps.stores.tenancy import resolve_admin

        resolve_admin(request, "admin")
        s.delete_page(request.admin.store, key)
        return Response({"ok": True})


class PagePublishView(AdminView):
    @extend_schema(summary="Publish draft", request=None, responses={200: dict})
    def post(self, request, key):
        return Response({"page": s.serialize(s.publish_page(request.admin.store, key))})


class PageUnpublishView(AdminView):
    @extend_schema(summary="Unpublish", request=None, responses={200: dict})
    def post(self, request, key):
        return Response({"page": s.serialize(s.unpublish_page(request.admin.store, key))})


class PageDuplicateView(AdminView):
    @extend_schema(summary="Duplicate (unique slug, fresh block ids)", request=None, responses={201: dict})
    def post(self, request, key):
        return Response({"page": s.serialize(s.duplicate_page(request.admin.store, key))}, status=201)


class PublicPageView(PublicView):
    @extend_schema(
        summary="Published page by id or slug (storefront)",
        parameters=[OpenApiParameter("id", str), OpenApiParameter("slug", str)],
        responses={200: dict, 404: dict},
    )
    def get(self, request):
        store = resolve_public_store(request)
        key, slug = request.query_params.get("id"), request.query_params.get("slug")
        if not key and not slug:
            raise bad_request("id یا slug لازم است")
        page = s.get_published(store, key) if key else s.get_published_by_slug(store, slug)
        if not page:
            raise not_found("صفحه یافت نشد")
        return Response({"page": s.public_serialize(page)})

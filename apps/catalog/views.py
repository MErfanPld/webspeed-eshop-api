from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response

from apps.core.errors import not_found
from apps.core.pagination import paginate
from apps.core.views import AdminView, PublicView, body
from apps.stores.tenancy import resolve_public_store

from . import services as s
from .models import Category, Product


class AdminProductListView(AdminView):
    write_role = "admin"

    @extend_schema(summary="All products of the current store (incl. drafts)", operation_id="admin_products_list", responses={200: dict})
    def get(self, request):
        qs = Product.objects.select_related("category").filter(store=request.admin.store).order_by("-created_at")
        return Response({"products": [s.serialize_product(p, admin=True) for p in qs]})

    @extend_schema(summary="Create product (admin+)", request=dict, responses={201: dict})
    def post(self, request):
        p = s.save_product(request.admin.store, body(request))
        return Response({"product": s.serialize_product(p, admin=True)}, status=201)


class AdminProductDetailView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Get product", responses={200: dict})
    def get(self, request, key):
        return Response({"product": s.serialize_product(s.get_product(request.admin.store, key), admin=True)})

    @extend_schema(summary="Update product (admin+)", request=dict, responses={200: dict})
    def put(self, request, key):
        p = s.save_product(request.admin.store, body(request), key)
        return Response({"product": s.serialize_product(p, admin=True)})

    @extend_schema(summary="Delete product (admin+)", responses={200: dict})
    def delete(self, request, key):
        s.delete_product(request.admin.store, key)
        return Response({"ok": True})


class AdminCategoryListView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Categories of the current store", responses={200: dict})
    def get(self, request):
        qs = Category.objects.filter(store=request.admin.store)
        return Response({"categories": [s.serialize_category(c) for c in qs]})

    @extend_schema(summary="Create category (admin+)", request=dict, responses={201: dict})
    def post(self, request):
        c = s.save_category(request.admin.store, body(request))
        return Response({"category": s.serialize_category(c)}, status=201)


class AdminCategoryDetailView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Update category (admin+)", request=dict, responses={200: dict})
    def put(self, request, key):
        return Response({"category": s.serialize_category(s.save_category(request.admin.store, body(request), key))})

    @extend_schema(summary="Delete category (admin+)", responses={200: dict})
    def delete(self, request, key):
        s.delete_category(request.admin.store, key)
        return Response({"ok": True})


class PublicProductListView(PublicView):
    @extend_schema(
        summary="Active products (paginated, filterable)", operation_id="products_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in ("page", "pageSize", "category", "gender", "q", "sort", "featured", "new", "minPrice", "maxPrice", "ids")
        ],
        responses={200: dict},
    )
    def get(self, request):
        store = resolve_public_store(request)
        items, meta = paginate(s.public_products(store, request.query_params), request, default_size=24)
        return Response({"products": [s.serialize_product(p) for p in items], "pagination": meta})


class PublicProductDetailView(PublicView):
    @extend_schema(summary="Active product by slug", responses={200: dict, 404: dict})
    def get(self, request, slug):
        store = resolve_public_store(request)
        p = Product.objects.select_related("category").filter(store=store, slug=slug, status="active").first()
        if not p:
            raise not_found("محصول یافت نشد")
        return Response({"product": s.serialize_product(p)})


class PublicCategoryListView(PublicView):
    @extend_schema(summary="Categories (storefront)", responses={200: dict})
    def get(self, request):
        store = resolve_public_store(request)
        return Response({"categories": [s.serialize_category(c) for c in Category.objects.filter(store=store)]})

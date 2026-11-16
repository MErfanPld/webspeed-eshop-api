from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response

from apps.core.errors import not_found
from apps.core.models import audit
from apps.core.pagination import paginate, paginate_optional
from apps.core.views import AdminView, PublicView, body
from apps.stores.tenancy import resolve_public_store

from . import services as s
from .models import Brand, Category, Product, Review


class AdminProductListView(AdminView):
    write_role = "admin"

    @extend_schema(
        summary="All products of the current store (incl. drafts)",
        operation_id="admin_products_list",
        responses={200: dict},
    )
    def get(self, request):
        qs = (
            Product.objects.select_related("category", "brand_ref")
            .filter(store=request.admin.store)
            .order_by("-created_at")
        )
        qp = request.query_params
        if qp.get("q"):
            qs = qs.filter(Q(name__icontains=qp["q"][:60]) | Q(slug__icontains=qp["q"][:60]))
        if qp.get("status") in Product.Status.values:
            qs = qs.filter(status=qp["status"])
        if qp.get("category"):
            qs = qs.filter(category__key=qp["category"])
        items, meta = paginate_optional(qs, request, 2000)
        out = {"products": [s.serialize_product(p, admin=True) for p in items]}
        if meta:
            out["pagination"] = meta
        return Response(out)

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
        audit(request.admin, "product.delete", key)
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
        summary="Active products (paginated, filterable)",
        operation_id="products_list",
        parameters=[
            OpenApiParameter(n, str)
            for n in (
                "page",
                "pageSize",
                "category",
                "brand",
                "gender",
                "q",
                "sort",
                "featured",
                "new",
                "minPrice",
                "maxPrice",
                "ids",
            )
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
        p = (
            Product.objects.select_related("category", "brand_ref")
            .filter(store=store, slug=slug, status="active")
            .first()
        )
        if not p:
            raise not_found("محصول یافت نشد")
        out = s.serialize_product(p)
        approved = [s.serialize_review(r) for r in p.review_set.filter(status="approved")[:50]]
        if approved:
            out["reviews"] = approved + list(out.get("reviews") or [])
        return Response({"product": out})


class PublicCategoryListView(PublicView):
    @extend_schema(summary="Categories (storefront)", responses={200: dict})
    def get(self, request):
        store = resolve_public_store(request)
        return Response({"categories": [s.serialize_category(c) for c in Category.objects.filter(store=store)]})


# --- Brands --------------------------------------------------------------------
class AdminBrandListView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Brands of the current store", responses={200: dict})
    def get(self, request):
        qs = Brand.objects.filter(store=request.admin.store).annotate(n=Count("products"))
        return Response({"brands": [s.serialize_brand(b, b.n) for b in qs]})

    @extend_schema(summary="Create brand (admin+)", request=dict, responses={201: dict})
    def post(self, request):
        return Response({"brand": s.serialize_brand(s.save_brand(request.admin.store, body(request)))}, status=201)


class AdminBrandDetailView(AdminView):
    write_role = "admin"

    @extend_schema(summary="Update brand (admin+)", request=dict, responses={200: dict})
    def put(self, request, brand_id):
        return Response({"brand": s.serialize_brand(s.save_brand(request.admin.store, body(request), brand_id))})

    @extend_schema(summary="Delete brand (admin+)", responses={200: dict})
    def delete(self, request, brand_id):
        s.delete_brand(request.admin.store, brand_id)
        audit(request.admin, "brand.delete", brand_id)
        return Response({"ok": True})


class PublicBrandListView(PublicView):
    @extend_schema(summary="Brands with active products (storefront)", responses={200: dict})
    def get(self, request):
        store = resolve_public_store(request)
        qs = (
            Brand.objects.filter(store=store)
            .annotate(n=Count("products", filter=Q(products__status="active")))
            .filter(n__gt=0)
        )
        return Response({"brands": [s.serialize_brand(b, b.n) for b in qs]})


# --- Reviews -------------------------------------------------------------------
class ProductReviewView(PublicView):
    @extend_schema(
        summary="Submit a review {rating 1-5, text} (signed-in buyers only; moderated)",
        request=dict,
        responses={201: dict},
    )
    def post(self, request, slug):
        from apps.core import ratelimit
        from apps.core.authentication import enforce_origin
        from apps.customers.views import current_customer

        enforce_origin(request)
        customer = current_customer(request)
        ratelimit.enforce(f"review:{customer.id}", 5, 3600, "تعداد نظرها زیاد بود؛ بعداً تلاش کنید.")
        p = Product.objects.filter(store=customer.store, slug=slug, status="active").first()
        if not p:
            raise not_found("محصول یافت نشد")
        r = s.add_review(customer.store, customer, p, body(request))
        return Response({"review": s.serialize_review(r), "status": r.status}, status=201)


class AdminReviewListView(AdminView):
    @extend_schema(summary="Reviews (filter ?status=pending|approved|rejected)", responses={200: dict})
    def get(self, request):
        qs = Review.objects.select_related("product").filter(store=request.admin.store)
        st = request.query_params.get("status")
        if st in Review.Status.values:
            qs = qs.filter(status=st)
        items, meta = paginate_optional(qs, request, 500)
        out = {"reviews": [s.serialize_review(r, admin=True) for r in items]}
        if meta:
            out["pagination"] = meta
        return Response(out)


class AdminReviewDetailView(AdminView):
    @extend_schema(summary="Moderate review {status}", request=dict, responses={200: dict})
    def patch(self, request, review_id):
        r = s.moderate_review(request.admin.store, review_id, body(request).get("status"))
        audit(request.admin, "review.moderate", review_id, status=r.status)
        return Response({"review": s.serialize_review(r, admin=True)})

    @extend_schema(summary="Delete review", responses={200: dict})
    def delete(self, request, review_id):
        r = Review.objects.select_related("product").filter(store=request.admin.store, id=review_id).first()
        if not r:
            raise not_found("نظر یافت نشد")
        product = r.product
        r.delete()
        s.recompute_rating(product)
        return Response({"ok": True})

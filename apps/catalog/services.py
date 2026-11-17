"""
Catalog rules (ported from frontend src/server/services/catalog.ts).
"""

import re
import secrets
import time

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.core.errors import bad_request, conflict, not_found
from apps.core.validators import CATALOG_SLUG_RE, sanitize_urls
from apps.stores.models import Store

from .models import Brand, Category, Product, Review

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def _str(v, max_len=500) -> str:
    return v.strip()[:max_len] if isinstance(v, str) else ""


def _int(v, minimum=0) -> int:
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        return minimum
    return n if n >= minimum else minimum


def serialize_category(c: Category) -> dict:
    out = {"id": c.key, "name": c.name, "slug": c.slug}
    if c.image:
        out["image"] = c.image
    return out


def serialize_product(p: Product, admin: bool = False) -> dict:
    """Frontend `Product` shape (camelCase). Admin adds status/timestamps."""
    variants = p.variants or {}
    out = {
        "id": p.key,
        "slug": p.slug,
        "name": p.name,
        "description": p.description,
        "price": p.price,
        "category": p.category.slug if p.category_id else "",
        "gender": p.gender,
        "images": p.images or [],
        "sizes": variants.get("sizes", []),
        "colors": variants.get("colors", []),
        "featured": p.featured,
        "newArrival": p.new_arrival,
        "stock": p.stock,
        "freeShipping": p.free_shipping,
        "tags": p.tags or [],
    }
    if p.brand_ref_id:
        out["brandSlug"] = p.brand_ref.slug
    for k, v in (
        ("compareAtPrice", p.compare_at_price),
        ("brand", p.brand or None),
        ("rating", p.rating),
        ("reviewCount", p.review_count),
        ("specs", p.specs),
        ("reviews", p.reviews),
    ):
        if v is not None:
            out[k] = v
    if admin:
        out.update({"status": p.status, "createdAt": _iso(p.created_at), "updatedAt": _iso(p.updated_at)})
    return out


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9\u0600-\u06FF]+", "-", name.strip().lower()).strip("-")
    return s or "brand"


def resolve_brand(store: Store, value) -> Brand | None:
    """Brand by slug or name within the store; a new name creates the brand."""
    name = _str(value, 80)
    if not name:
        return None
    brand = Brand.objects.filter(store=store).filter(Q(slug=name.lower()) | Q(name=name)).first()
    if brand:
        return brand
    base, i = _slugify(name), 2
    slug = base
    while Brand.objects.filter(store=store, slug=slug).exists():
        slug, i = f"{base}-{i}", i + 1
    return Brand.objects.create(store=store, slug=slug, name=name)


def normalize_product_input(store: Store, data: dict) -> dict:
    if not isinstance(data, dict):
        raise bad_request("اطلاعات محصول نامعتبر است")
    name = _str(data.get("name"), 200)
    if not name:
        raise bad_request("نام محصول الزامی است")
    slug = _str(data.get("slug"), 120).lower()
    if not CATALOG_SLUG_RE.match(slug):
        raise bad_request("اسلاگ فقط شامل حروف، عدد و - باشد")
    price = _int(data.get("price"))
    if price <= 0:
        raise bad_request("قیمت باید بیشتر از صفر باشد")
    compare = _int(data.get("compareAtPrice")) if data.get("compareAtPrice") else None
    if compare is not None and compare > 0 and compare <= price:
        raise bad_request("قیمت قبل از تخفیف باید از قیمت فروش بیشتر باشد")
    gender = data.get("gender") if data.get("gender") in ("men", "women", "unisex") else "unisex"
    status = data.get("status") if data.get("status") in ("active", "draft", "archived") else "draft"

    def str_list(v, limit=50, max_len=80):
        return [s for s in (_str(x, max_len) for x in v) if s][:limit] if isinstance(v, list) else []

    images = str_list(data.get("images"), 12, 500)
    colors = []
    if isinstance(data.get("colors"), list):
        for c in data["colors"][:20]:
            if not isinstance(c, dict):
                continue
            cname = _str(c.get("name"), 40)
            if cname:
                hexv = c.get("hex") if isinstance(c.get("hex"), str) and HEX_RE.match(c["hex"]) else "#000000"
                colors.append({"name": cname, "hex": hexv})

    category = None
    cat_slug = _str(data.get("category"), 80)
    if cat_slug:
        # Category must belong to the same store
        category = Category.objects.filter(store=store, slug=cat_slug).first()
        if not category:
            raise bad_request("دسته‌بندی انتخاب‌شده وجود ندارد")

    specs = data.get("specs") if isinstance(data.get("specs"), dict) else None
    if specs:
        specs = {_str(k, 80): _str(v, 300) for k, v in list(specs.items())[:40] if _str(k, 80)}

    return sanitize_urls(
        {
            "name": name,
            "slug": slug,
            "description": _str(data.get("description"), 5000),
            "price": price,
            "compare_at_price": compare if compare and compare > 0 else None,
            "category": category,
            "gender": gender,
            "brand_ref": resolve_brand(store, data.get("brand")),
            "images": images,
            "variants": {"sizes": str_list(data.get("sizes")), "colors": colors},
            "featured": bool(data.get("featured")),
            "new_arrival": bool(data.get("newArrival")),
            "free_shipping": bool(data.get("freeShipping")),
            "stock": _int(data.get("stock")),
            "tags": str_list(data.get("tags")),
            "specs": specs,
            "status": status,
        }
    )


def get_product(store: Store, key: str) -> Product:
    p = Product.objects.select_related("category", "brand_ref").filter(store=store, key=key).first()
    if not p:
        raise not_found("محصول یافت نشد")
    return p


@transaction.atomic
def save_product(store: Store, data: dict, key: str | None = None) -> Product:
    values = normalize_product_input(store, data)
    if key:
        product = Product.objects.select_for_update().filter(store=store, key=key).first()
        if not product:
            raise not_found("محصول یافت نشد")
    else:
        from apps.platform.services import enforce_product_limit

        enforce_product_limit(store)
        product = Product(store=store, key=f"p-{int(time.time() * 1000):x}-{secrets.token_hex(2)}")
    clash = Product.objects.filter(store=store, slug=values["slug"]).exclude(pk=product.pk)
    if clash.exists():
        raise conflict("این اسلاگ قبلاً استفاده شده")
    for k, v in values.items():
        setattr(product, k, v)
    product.brand = product.brand_ref.name if product.brand_ref else ""
    try:
        product.save()
    except IntegrityError:
        raise conflict("این اسلاگ قبلاً استفاده شده") from None
    return product


def delete_product(store: Store, key: str):
    deleted, _ = Product.objects.filter(store=store, key=key).delete()
    if not deleted:
        raise not_found("محصول یافت نشد")


SORTS = {
    "newest": "-created_at",
    "price-asc": "price",
    "price-desc": "-price",
    "bestsellers": "-review_count",
    "featured": "-featured",
}


def public_products(store: Store, params) -> "QuerySet[Product]":  # noqa: F821
    qs = Product.objects.select_related("category", "brand_ref").filter(store=store, status=Product.Status.ACTIVE)
    if params.get("brand"):
        qs = qs.filter(brand_ref__slug=params["brand"])
    if params.get("category"):
        qs = qs.filter(category__slug=params["category"])
    if params.get("gender") in ("men", "women", "unisex"):
        qs = qs.filter(gender=params["gender"])
    if params.get("q"):
        q = params["q"].strip()[:100]
        qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(tags__icontains=q))
    if params.get("featured") in ("1", "true"):
        qs = qs.filter(featured=True)
    if params.get("new") in ("1", "true"):
        qs = qs.filter(new_arrival=True)
    for key, lookup in (("minPrice", "price__gte"), ("maxPrice", "price__lte")):
        if params.get(key, "").isdigit():
            qs = qs.filter(**{lookup: int(params[key])})
    if params.get("ids"):
        qs = qs.filter(key__in=[x for x in params["ids"].split(",") if x][:100])
    return qs.order_by(SORTS.get(params.get("sort", ""), "-created_at"), "-created_at")


# --- Categories --------------------------------------------------------------


@transaction.atomic
def save_category(store: Store, data: dict, key: str | None = None) -> Category:
    name = _str(data.get("name"), 80)
    slug = _str(data.get("slug"), 80).lower()
    if not name:
        raise bad_request("نام دسته الزامی است")
    if not CATALOG_SLUG_RE.match(slug):
        raise bad_request("اسلاگ دسته نامعتبر است")
    if key:
        cat = Category.objects.select_for_update().filter(store=store, key=key).first()
        if not cat:
            raise not_found("دسته یافت نشد")
    else:
        cat = Category(store=store, key=f"c-{int(time.time() * 1000):x}")
    if Category.objects.filter(store=store, slug=slug).exclude(pk=cat.pk).exists():
        raise conflict("این اسلاگ قبلاً استفاده شده")
    cat.name = name
    cat.slug = slug
    cat.image = sanitize_urls({"image": _str(data.get("image"), 500)})["image"]
    cat.sort = _int(data.get("sort"))
    cat.save()
    return cat


def delete_category(store: Store, key: str):
    deleted, _ = Category.objects.filter(store=store, key=key).delete()
    if not deleted:
        raise not_found("دسته یافت نشد")


# --- Brands ------------------------------------------------------------------


def serialize_brand(b: Brand, count: int | None = None) -> dict:
    out = {"id": b.id, "slug": b.slug, "name": b.name, "logo": b.logo or ""}
    if count is not None:
        out["products"] = count
    return out


@transaction.atomic
def save_brand(store: Store, data: dict, brand_id: int | None = None) -> Brand:
    name = _str(data.get("name"), 80)
    slug = _str(data.get("slug"), 80).lower()
    if not name:
        raise bad_request("نام برند الزامی است")
    if not CATALOG_SLUG_RE.match(slug):
        raise bad_request("اسلاگ برند نامعتبر است")
    if brand_id:
        brand = Brand.objects.select_for_update().filter(store=store, id=brand_id).first()
        if not brand:
            raise not_found("برند یافت نشد")
    else:
        brand = Brand(store=store)
    if Brand.objects.filter(store=store, slug=slug).exclude(pk=brand.pk).exists():
        raise conflict("این اسلاگ قبلاً استفاده شده")
    brand.name, brand.slug = name, slug
    brand.logo = sanitize_urls({"logo": _str(data.get("logo"), 500)})["logo"]
    brand.save()
    # keep the denormalized display name in sync
    Product.objects.filter(store=store, brand_ref=brand).update(brand=brand.name)
    return brand


def delete_brand(store: Store, brand_id: int):
    brand = Brand.objects.filter(store=store, id=brand_id).first()
    if not brand:
        raise not_found("برند یافت نشد")
    Product.objects.filter(store=store, brand_ref=brand).update(brand="", brand_ref=None)
    brand.delete()


# --- Reviews -----------------------------------------------------------------


def serialize_review(r: Review, admin: bool = False) -> dict:
    out = {
        "id": r.id,
        "user": r.author,
        "rating": r.rating,
        "comment": r.text,
        "date": _iso(r.created_at),
    }
    if admin:
        out.update({"status": r.status, "productId": r.product.key, "productName": r.product.name})
    return out


def recompute_rating(product: Product):
    from django.db.models import Avg, Count

    agg = Review.objects.filter(product=product, status=Review.Status.APPROVED).aggregate(
        a=Avg("rating"), c=Count("id")
    )
    if agg["c"]:
        product.rating = round(agg["a"], 1)
        product.review_count = agg["c"]
        product.save(update_fields=["rating", "review_count", "updated_at"])


def add_review(store: Store, customer, product: Product, data: dict) -> Review:
    from apps.orders.models import Order

    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        rating = 0
    text = _str(data.get("text"), 2000)
    if not 1 <= rating <= 5:
        raise bad_request("امتیاز باید بین ۱ تا ۵ باشد")
    if len(text) < 3:
        raise bad_request("متن نظر را بنویسید")
    bought = Order.objects.filter(store=store, customer=customer, items__contains=[{"productId": product.key}]).exclude(
        status=Order.Status.CANCELLED
    )
    if not bought.exists():
        raise bad_request("فقط خریداران این محصول می‌توانند نظر ثبت کنند")
    if Review.objects.filter(product=product, customer=customer).exists():
        raise conflict("شما قبلاً برای این محصول نظر ثبت کرده‌اید")
    return Review.objects.create(
        store=store, product=product, customer=customer, author=customer.name or "مشتری", rating=rating, text=text
    )


@transaction.atomic
def moderate_review(store: Store, review_id: int, status: str) -> Review:
    if status not in (Review.Status.APPROVED, Review.Status.REJECTED, Review.Status.PENDING):
        raise bad_request("وضعیت نامعتبر است")
    r = Review.objects.select_related("product").select_for_update().filter(store=store, id=review_id).first()
    if not r:
        raise not_found("نظر یافت نشد")
    r.status = status
    r.save(update_fields=["status"])
    recompute_rating(r.product)
    return r

from django.db import models
from django.db.models import Q

from apps.stores.models import Store


class Category(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="categories")
    key = models.CharField(max_length=80)
    slug = models.CharField(max_length=80)
    name = models.CharField(max_length=80)
    image = models.CharField(max_length=500, blank=True)
    sort = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort", "slug"]
        constraints = [
            models.UniqueConstraint(fields=["store", "key"], name="uniq_category_key_per_store"),
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_category_slug_per_store"),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        DRAFT = "draft"
        ARCHIVED = "archived"

    class Gender(models.TextChoices):
        MEN = "men"
        WOMEN = "women"
        UNISEX = "unisex"

    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="products")
    key = models.CharField(max_length=80)
    slug = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.BigIntegerField()
    compare_at_price = models.BigIntegerField(null=True, blank=True)
    stock = models.IntegerField(default=0)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.UNISEX)
    brand = models.CharField(max_length=80, blank=True)
    images = models.JSONField(default=list, blank=True)
    # {"sizes": ["S","M"], "colors": [{"name": "مشکی", "hex": "#111111"}]}
    variants = models.JSONField(default=dict, blank=True)
    featured = models.BooleanField(default=False)
    new_arrival = models.BooleanField(default=False)
    free_shipping = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    specs = models.JSONField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    review_count = models.IntegerField(null=True, blank=True)
    reviews = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "key"], name="uniq_product_key_per_store"),
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_product_slug_per_store"),
            models.CheckConstraint(condition=Q(price__gt=0), name="product_price_positive"),
            models.CheckConstraint(condition=Q(stock__gte=0), name="product_stock_non_negative"),
        ]
        indexes = [
            models.Index(fields=["store", "status", "-created_at"]),
            models.Index(fields=["store", "category"]),
        ]

    def __str__(self):
        return self.name

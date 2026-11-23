"""Sample products: replace the six shared grey placeholders with artwork that
matches each product's category and color (frontend public/placeholders/products).
Only images that are still the original placeholders are changed."""
import re

from django.db import migrations

CATEGORY_ART = {"t-shirts", "shirts", "hoodies", "jackets", "pants", "jeans", "dresses", "accessories"}
COLOR_WORDS = [("مشکی", 1), ("کرم", 2), ("زیتونی", 3), ("سفید", 7), ("خاکستری", 7), ("آبی", 4), ("جین", 4), ("صورتی", 5)]
OLD = re.compile(r"^/placeholders/product-\d\.svg$")


def art_for(category: str, name: str, key: str) -> list[str]:
    cat = category if category in CATEGORY_ART else "default"
    palette = next((n for word, n in COLOR_WORDS if word in name), sum(map(ord, key)) % 8 + 1)
    second = (palette + 2) % 8 + 1
    return [f"/placeholders/products/{cat}-{palette}.svg", f"/placeholders/products/{cat}-{second}.svg"]


def forward(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    for p in Product.objects.select_related("category").iterator():
        images = p.images or []
        if images and all(isinstance(i, str) and OLD.match(i) for i in images):
            p.images = art_for(p.category.slug if p.category else "", p.name, p.key)
            p.save(update_fields=["images"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0004_category_banners")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]

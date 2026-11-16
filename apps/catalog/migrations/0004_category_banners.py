"""Switch the sample categories from grey placeholders to the generated banners
(only rows still using the original placeholder, so custom images are kept)."""
from django.db import migrations

SLUGS = ["t-shirts", "shirts", "hoodies", "jackets", "pants", "jeans", "accessories"]


def forward(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for c in Category.objects.filter(slug__in=SLUGS, image__startswith="/placeholders/cat-"):
        c.image = f"/banners/{c.slug}.svg"
        c.save(update_fields=["image"])

    # Home page "category grid" blocks keep their own copy of the image URL
    import re

    pattern = re.compile(r"/placeholders/cat-\d\.svg")
    Page = apps.get_model("pages", "Page")

    def fix(node):
        if isinstance(node, list):
            return [fix(n) for n in node]
        if isinstance(node, dict):
            if isinstance(node.get("image"), str) and pattern.fullmatch(node["image"]) and node.get("slug") in SLUGS:
                node = {**node, "image": f"/banners/{node['slug']}.svg"}
            return {k: fix(v) for k, v in node.items()}
        return node

    for page in Page.objects.all():
        doc, published = fix(page.doc), fix(page.published_blocks)
        if doc != page.doc or published != page.published_blocks:
            page.doc, page.published_blocks = doc, published
            page.save(update_fields=["doc", "published_blocks"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_brands_from_text"), ("pages", "0002_savedblock")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]

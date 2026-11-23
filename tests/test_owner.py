from rest_framework.test import APIClient

from apps.platform.models import Article, FaqItem, Plan, Subscription

from .base import ApiTestCase

ORIGIN = "http://localhost:3000"


class OwnerPanelTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.owner.is_superuser = True
        self.owner.save()

    def test_only_superusers(self):
        self.make_user("e@test.local", "admin")
        c = self.client_for("e@test.local")
        for path in ["/api/v1/platform/overview", "/api/v1/platform/admin/plans", "/api/v1/platform/admin/landing", "/api/v1/platform/admin/articles"]:
            self.assertEqual(c.get(path).status_code, 403, path)
        self.assertEqual(APIClient().get("/api/v1/platform/overview").status_code, 401)

    def test_overview_numbers(self):
        Subscription.objects.create(store=self.store, plan=Plan.objects.get(slug="pro"), status="active")
        d = self.client.get("/api/v1/platform/overview").json()
        self.assertEqual(d["stores"]["total"], 1)
        self.assertEqual(d["stores"]["paid"], 1)
        self.assertEqual(d["mrr"], Plan.objects.get(slug="pro").price_monthly)
        self.assertIn("signups", d)

    def test_edit_plan_and_landing(self):
        r = self.client.patch("/api/v1/platform/admin/plans/starter", {"priceMonthly": 350000, "features": ["الف", "ب"], "highlighted": True}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Plan.objects.get(slug="starter").price_monthly, 350000)
        self.assertFalse(Plan.objects.get(slug="pro").highlighted)  # only one highlighted plan
        r = self.client.patch("/api/v1/platform/admin/landing", {"heroTitle": "تیتر تازه", "videoUrl": "javascript:alert(1)"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch("/api/v1/platform/admin/landing", {"heroTitle": "تیتر تازه"}, format="json")
        self.assertEqual(r.json()["settings"]["heroTitle"], "تیتر تازه")
        self.assertEqual(APIClient().get("/api/v1/platform/landing").json()["settings"]["heroTitle"], "تیتر تازه")

    def test_replace_faq_list_keeps_order_and_deletes_removed(self):
        items = self.client.get("/api/v1/platform/admin/content/faq").json()["items"]
        first, second = items[0], items[1]
        r = self.client.put(
            "/api/v1/platform/admin/content/faq",
            {"items": [second, {"question": "سؤال جدید", "answer": "پاسخ"}, first]},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([i["question"] for i in r.json()["items"]], [second["question"], "سؤال جدید", first["question"]])
        self.assertEqual(FaqItem.objects.count(), 3)
        bad = self.client.put("/api/v1/platform/admin/content/faq", {"items": [{"question": ""}]}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_article_crud(self):
        r = self.client.post(
            "/api/v1/platform/admin/articles",
            {"title": "مقاله تست", "slug": "test-article", "excerpt": "خلاصه", "body": "## تیتر\\n\\nمتن", "status": "draft"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        aid = r.json()["article"]["id"]
        self.assertEqual(APIClient().get("/api/v1/platform/articles/test-article").status_code, 404)  # draft hidden
        r = self.client.put(f"/api/v1/platform/admin/articles/{aid}", {**r.json()["article"], "status": "published"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(APIClient().get("/api/v1/platform/articles/test-article").status_code, 200)
        dup = self.client.post("/api/v1/platform/admin/articles", {"title": "x", "slug": "test-article", "excerpt": "x", "body": "x"}, format="json")
        self.assertEqual(dup.status_code, 400)
        self.assertEqual(self.client.delete(f"/api/v1/platform/admin/articles/{aid}").status_code, 200)
        self.assertFalse(Article.objects.filter(pk=aid).exists())

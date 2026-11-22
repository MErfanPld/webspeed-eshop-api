from django.core.cache import cache
from rest_framework.test import APIClient

from apps.platform.models import Article, FaqItem, LandingSettings, Testimonial

from .base import ApiTestCase


class LandingContentTests(ApiTestCase):
    def test_landing_payload_has_seeded_content_and_real_stats(self):
        d = APIClient().get("/api/v1/platform/landing").json()
        self.assertEqual(len(d["features"]), 9)
        self.assertEqual(len(d["roadmap"]), 6)
        self.assertEqual(len(d["faq"]), 5)
        self.assertEqual(d["testimonials"], [])  # never invented
        self.assertEqual(len(d["articles"]), 3)
        self.assertEqual(d["stats"]["stores"], 1)  # the seeded store, from the database
        self.assertEqual(len(d["plans"]), 3)

    def test_admin_edits_show_up_immediately(self):
        APIClient().get("/api/v1/platform/landing")  # warm the cache
        st = LandingSettings.load()
        st.hero_title = "عنوان تازه"
        st.video_url = "https://www.aparat.com/v/abc123"
        st.show_stats = False
        st.save()
        Testimonial.objects.create(name="مشتری واقعی", text="عالی", sort=0)
        FaqItem.objects.filter(sort=0).update(active=False)  # .update() skips signals …
        cache.clear()  # … so clear explicitly for that one
        d = APIClient().get("/api/v1/platform/landing").json()
        self.assertEqual(d["settings"]["heroTitle"], "عنوان تازه")
        self.assertEqual(d["settings"]["videoUrl"], "https://www.aparat.com/v/abc123")
        self.assertIsNone(d["stats"])
        self.assertEqual(d["testimonials"][0]["name"], "مشتری واقعی")
        self.assertEqual(len(d["faq"]), 4)

    def test_articles_list_detail_and_drafts_hidden(self):
        Article.objects.create(title="پیش‌نویس", slug="draft-one", excerpt="x", body="y", status="draft")
        lst = APIClient().get("/api/v1/platform/articles").json()
        self.assertEqual(len(lst["articles"]), 3)
        self.assertIn("آموزش", lst["categories"])
        self.assertEqual(APIClient().get("/api/v1/platform/articles/draft-one").status_code, 404)
        a = APIClient().get("/api/v1/platform/articles/start-online-shop").json()
        self.assertIn("## ", a["article"]["body"])
        self.assertEqual(len(a["related"]), 2)

    def test_settings_is_a_singleton(self):
        LandingSettings(hero_title="دوم").save()
        self.assertEqual(LandingSettings.objects.count(), 1)
        self.assertEqual(LandingSettings.load().hero_title, "دوم")

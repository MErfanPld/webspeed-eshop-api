from rest_framework.test import APIClient

from .base import ORIGIN, PASSWORD, ApiTestCase


class AuthTests(ApiTestCase):
    def test_seed_creates_store_owner_pages_and_catalog(self):
        from apps.catalog.models import Category, Product
        from apps.pages.models import Page

        self.assertEqual(Product.objects.filter(store=self.store).count(), 20)
        self.assertEqual(Category.objects.filter(store=self.store).count(), 8)
        keys = set(Page.objects.filter(store=self.store).values_list("key", flat=True))
        self.assertEqual(keys, {"home", "site-header", "site-footer", "about", "contact"})
        self.assertTrue(self.owner.password.startswith("md5$") or self.owner.password.startswith("argon2"))

    def test_login_success_and_me(self):
        data = self.login()
        self.assertIn("refresh", data)
        r = self.client.get("/api/v1/auth/me")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["store"]["role"], "owner")

    def test_wrong_password_persian_error(self):
        r = self.client.post("/api/v1/auth/login", {"email": "owner@test.local", "password": "x"}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"error": "ایمیل یا رمز عبور اشتباه است.", "details": None})

    def test_login_rate_limited(self):
        for _ in range(8):
            self.client.post("/api/v1/auth/login", {"email": "owner@test.local", "password": "x"}, format="json")
        r = self.client.post("/api/v1/auth/login", {"email": "owner@test.local", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 429)
        self.assertIn("retryAfter", r.json()["details"])

    def test_successful_login_resets_the_limit(self):
        for _ in range(7):
            self.client.post("/api/v1/auth/login", {"email": "owner@test.local", "password": "x"}, format="json")
        self.login()
        for _ in range(7):
            self.client.post("/api/v1/auth/login", {"email": "owner@test.local", "password": "x"}, format="json")
        r = self.client.post("/api/v1/auth/login", {"email": "owner@test.local", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_admin_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/admin/pages").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        self.assertEqual(self.client.get("/api/v1/admin/pages").status_code, 401)

    def test_refresh_rotates_and_blacklists(self):
        tokens = self.login()
        r = self.client.post("/api/v1/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(r.status_code, 200)
        # old refresh can't be reused
        r2 = self.client.post("/api/v1/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(r2.status_code, 401)

    def test_logout_revokes_refresh(self):
        tokens = self.login()
        self.client.post("/api/v1/auth/logout", {"refresh": tokens["refresh"]}, format="json")
        r = self.client.post("/api/v1/auth/refresh", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_cookie_auth_requires_trusted_origin_for_writes(self):
        c = APIClient()
        c.post("/api/v1/auth/login", {"email": "owner@test.local", "password": PASSWORD}, format="json")
        self.assertEqual(c.get("/api/v1/admin/pages").status_code, 200)  # safe method
        r = c.post("/api/v1/admin/pages", {"name": "x", "slug": "/x"}, format="json")
        self.assertEqual(r.status_code, 403)
        r = c.post("/api/v1/admin/pages", {"name": "x", "slug": "/x"}, format="json", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(r.status_code, 403)
        r = c.post("/api/v1/admin/pages", {"name": "x", "slug": "/x"}, format="json", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 201)

    def test_argon2_is_default_hasher(self):
        from django.conf import settings

        from config.settings import base

        self.assertEqual(base.PASSWORD_HASHERS[0], "django.contrib.auth.hashers.Argon2PasswordHasher")
        self.assertTrue(settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"])


class EmptyEnvValueTests(ApiTestCase):
    def test_empty_jwt_signing_key_falls_back_to_secret_key(self):
        import importlib
        import os

        from config.settings import base

        old = os.environ.get("JWT_SIGNING_KEY")
        os.environ["JWT_SIGNING_KEY"] = ""
        try:
            reloaded = importlib.reload(base)
            self.assertEqual(reloaded.SIMPLE_JWT["SIGNING_KEY"], reloaded.SECRET_KEY)
            self.assertIsNone(reloaded.JWT_COOKIE_DOMAIN or None)
        finally:
            if old is None:
                os.environ.pop("JWT_SIGNING_KEY", None)
            else:
                os.environ["JWT_SIGNING_KEY"] = old
            importlib.reload(base)

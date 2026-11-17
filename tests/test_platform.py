from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Product
from apps.platform.models import Plan, Subscription
from apps.stores.models import Store, StoreMember

from .base import PASSWORD, ApiTestCase

PD = "webspeed.test"
ORIGIN_A = f"https://alpha.{PD}"


@override_settings(PLATFORM_DOMAIN=PD, DEFAULT_STORE_SLUG="", CORS_ALLOWED_ORIGIN_REGEXES=[r"^https?://([a-z0-9-]+\.)?webspeed\.test$"])
class SubdomainIsolationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.a = Store.objects.create(name="آلفا", slug="alpha")
        self.b = Store.objects.create(name="بتا", slug="beta")
        Product.objects.create(store=self.a, key="pa", slug="pa", status="active", name="محصول آلفا", price=1000, stock=1)
        Product.objects.create(store=self.b, key="pb", slug="pb", status="active", name="محصول بتا", price=1000, stock=1)
        self.ua = self.make_user("a-owner@test.local", "owner", store=self.a)
        self.ub = self.make_user("b-owner@test.local", "owner", store=self.b)

    def get(self, path, host, client=None):
        return (client or APIClient()).get(path, HTTP_X_STORE_HOST=host)

    def test_each_subdomain_sees_only_its_own_catalog(self):
        a = [p["id"] for p in self.get("/api/v1/products", f"alpha.{PD}").json()["products"]]
        b = [p["id"] for p in self.get("/api/v1/products", f"beta.{PD}").json()["products"]]
        self.assertEqual(a, ["pa"])
        self.assertEqual(b, ["pb"])
        self.assertEqual(self.get("/api/v1/products/pb", f"alpha.{PD}").status_code, 404)
        self.assertEqual(self.get("/api/v1/store", f"beta.{PD}").json()["store"]["name"], "بتا")

    def test_unknown_reserved_and_platform_hosts_never_fall_back_to_a_store(self):
        for host in (f"nope.{PD}", f"panel.{PD}", f"www.{PD}", PD, "evil.example.com", f"a.b.{PD}"):
            self.assertEqual(self.get("/api/v1/store", host).status_code, 404, host)

    def test_platform_subdomains_never_fall_back_even_with_default_store(self):
        with self.settings(DEFAULT_STORE_SLUG="alpha"):
            for host in (f"nope.{PD}", f"panel.{PD}", PD):
                self.assertEqual(self.get("/api/v1/store", host).status_code, 404, host)
            # a foreign host (e.g. the server IP) may use the explicit default
            self.assertEqual(self.get("/api/v1/store", "10.0.0.5").json()["store"]["name"], "آلفا")

    def test_payment_returns_to_the_shops_own_address(self):
        from apps.orders.models import Order
        from apps.orders.payments import result_url

        o = Order(store=self.b, number="WS-1", customer_info={}, items=[], subtotal=0, total=0)
        with self.settings(DEBUG=False):
            self.assertTrue(result_url(o, True).startswith(f"https://beta.{PD}/checkout/result?"))
            self.b.domain = "shop-beta.com"
            self.assertTrue(result_url(o, True).startswith("https://shop-beta.com/checkout/result?"))

    def test_custom_domain_still_works(self):
        self.b.domain = "shop-beta.com"
        self.b.save()
        self.assertEqual(self.get("/api/v1/store", "shop-beta.com").json()["store"]["name"], "بتا")

    def admin_client(self, email, host):
        c = APIClient()
        r = c.post(
            "/api/v1/auth/login", {"email": email, "password": PASSWORD}, format="json",
            HTTP_X_STORE_HOST=host, HTTP_ORIGIN=f"https://{host}",
        )
        return c, r

    def test_store_panel_is_locked_to_its_subdomain(self):
        # owner of A cannot even sign in on B's host
        _, r = self.admin_client("a-owner@test.local", f"beta.{PD}")
        self.assertEqual(r.status_code, 401)
        c, r = self.admin_client("a-owner@test.local", f"alpha.{PD}")
        self.assertEqual(r.status_code, 200)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        # store A data on A's host
        products = c.get("/api/v1/admin/products", HTTP_X_STORE_HOST=f"alpha.{PD}").json()["products"]
        self.assertEqual([p["id"] for p in products], ["pa"])
        # asking for B with the same token on B's host is refused, even with X-Store-Id
        r = c.get("/api/v1/admin/products", HTTP_X_STORE_HOST=f"beta.{PD}", HTTP_X_STORE_ID=str(self.b.id))
        self.assertEqual(r.status_code, 403)
        # X-Store-Id can't override the host on A's subdomain either
        r = c.get("/api/v1/admin/store", HTTP_X_STORE_HOST=f"alpha.{PD}", HTTP_X_STORE_ID=str(self.b.id))
        self.assertEqual(r.json()["store"]["name"], "آلفا")

    def test_central_panel_switches_between_own_stores_only(self):
        StoreMember.objects.create(store=self.b, user=self.ua, role="admin")
        c, r = self.admin_client("a-owner@test.local", f"panel.{PD}")
        self.assertEqual(r.status_code, 200)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        r = c.get("/api/v1/admin/store", HTTP_X_STORE_HOST=f"panel.{PD}", HTTP_X_STORE_ID=str(self.b.id))
        self.assertEqual(r.json()["store"]["name"], "بتا")
        # a store the user doesn't belong to is never selected
        other = Store.objects.create(name="غریبه", slug="stranger")
        r = c.get("/api/v1/admin/store", HTTP_X_STORE_HOST=f"panel.{PD}", HTTP_X_STORE_ID=str(other.id))
        self.assertNotEqual(r.json()["store"]["name"], "غریبه")

    def test_subdomain_origins_are_trusted_for_writes(self):
        from apps.core.authentication import origin_allowed

        class R:
            META = {"HTTP_ORIGIN": ORIGIN_A}

            def get_host(self):
                return "api.internal"

        self.assertTrue(origin_allowed(R()))
        R.META = {"HTTP_ORIGIN": "https://alpha.webspeed.test.evil.com"}
        self.assertFalse(origin_allowed(R()))

    def test_expired_subscription_closes_the_storefront_only(self):
        Subscription.objects.create(
            store=self.a, plan=Plan.objects.get(slug="starter"), trial_ends_at=timezone.now() - timedelta(days=1)
        )
        r = self.get("/api/v1/store", f"alpha.{PD}")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["details"], {"reason": "inactive"})
        self.assertEqual(self.get("/api/v1/store", f"beta.{PD}").status_code, 200)
        c, r = self.admin_client("a-owner@test.local", f"alpha.{PD}")
        self.assertEqual(r.status_code, 200)  # the owner can still sign in and renew


@override_settings(PLATFORM_DOMAIN=PD, CORS_ALLOWED_ORIGIN_REGEXES=[r"^https?://([a-z0-9-]+\.)?webspeed\.test$"])
class SignupTests(ApiTestCase):
    def signup(self, **kw):
        data = {
            "storeName": "فروشگاه تازه", "subdomain": "tazeh", "name": "مالک", "email": "new@test.local",
            "password": "Sign-Up-Pass-2026", "plan": "pro", **kw,
        }
        return APIClient().post("/api/v1/platform/signup", data, format="json", HTTP_ORIGIN=f"https://{PD}")

    def test_plans_and_subdomain_check(self):
        plans = APIClient().get("/api/v1/platform/plans").json()["plans"]
        self.assertEqual([p["slug"] for p in plans], ["starter", "pro", "business"])
        check = lambda n: APIClient().get(f"/api/v1/platform/check-subdomain?name={n}").json()  # noqa: E731
        self.assertTrue(check("my-shop")["available"])
        self.assertFalse(check("panel")["available"])
        self.assertFalse(check("default")["available"])  # existing store
        self.assertFalse(check("Bad_Name")["available"])

    def test_signup_creates_isolated_store_with_trial(self):
        r = self.signup()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["store"]["adminUrl"], f"https://tazeh.{PD}/admin")
        store = Store.objects.get(slug="tazeh")
        self.assertEqual(store.subscription.plan.slug, "pro")
        self.assertEqual(store.subscription.status, "trial")
        self.assertEqual(StoreMember.objects.get(store=store).user.email, "new@test.local")
        self.assertEqual(Product.objects.filter(store=store).count(), 0)  # empty, never another store's data
        # new owner can sign in on the new subdomain only
        c = APIClient()
        ok = c.post("/api/v1/auth/login", {"email": "new@test.local", "password": "Sign-Up-Pass-2026"}, format="json",
                    HTTP_X_STORE_HOST=f"tazeh.{PD}")
        self.assertEqual(ok.status_code, 200)
        bad = c.post("/api/v1/auth/login", {"email": "new@test.local", "password": "Sign-Up-Pass-2026"}, format="json",
                     HTTP_X_STORE_HOST=f"default.{PD}")
        self.assertEqual(bad.status_code, 401)

    def test_signup_validation(self):
        self.signup()
        r = self.signup(subdomain="tazeh", email="other@test.local")
        self.assertEqual(r.json()["details"]["subdomain"], "این آدرس قبلاً گرفته شده")
        r = self.signup(subdomain="another", email="new@test.local")
        self.assertIn("email", r.json()["details"])
        r = self.signup(subdomain="www", email="x@test.local")
        self.assertIn("subdomain", r.json()["details"])
        r = self.signup(subdomain="weakpw", email="y@test.local", password="123")
        self.assertIn("password", r.json()["details"])

    def test_plan_product_limit(self):
        self.signup(plan="starter")
        store = Store.objects.get(slug="tazeh")
        Plan.objects.filter(slug="starter").update(max_products=1)
        Product.objects.create(store=store, key="x1", slug="x1", name="x", price=1, stock=1)
        c = APIClient()
        r = c.post("/api/v1/auth/login", {"email": "new@test.local", "password": "Sign-Up-Pass-2026"}, format="json",
                   HTTP_X_STORE_HOST=f"tazeh.{PD}")
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        r = c.post("/api/v1/admin/products", {"name": "y", "slug": "y", "price": 1, "stock": 1}, format="json",
                   HTTP_X_STORE_HOST=f"tazeh.{PD}")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["details"], {"reason": "plan_limit"})

    def test_platform_admin_only_for_superusers(self):
        self.login()
        self.assertEqual(self.client.get("/api/v1/platform/stores").status_code, 403)
        self.owner.is_superuser = True
        self.owner.save()
        data = self.client.get("/api/v1/platform/stores").json()
        self.assertGreaterEqual(data["stats"]["stores"], 1)
        st = Store.objects.get(slug="default")
        r = self.client.patch(
            f"/api/v1/platform/stores/{st.id}", {"plan": "business", "status": "active", "paidUntil": "2030-01-01"},
            format="json", HTTP_ORIGIN=f"https://panel.{PD}",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["store"]["subscription"]["plan"]["slug"], "business")
        self.assertTrue(r.json()["store"]["subscription"]["active"])

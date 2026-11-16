import base64
import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.seed import ensure_seeded
from apps.stores.models import Store, StoreMember
from apps.users.models import User

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
ORIGIN = "http://localhost:3000"
PASSWORD = "Str0ng-Pass!word"


class ApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        with override_settings(ADMIN_EMAIL="owner@test.local", ADMIN_PASSWORD=PASSWORD):
            ensure_seeded()
        cls.store = Store.objects.get(slug="default")
        cls.owner = User.objects.get(email="owner@test.local")

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    # -- helpers ------------------------------------------------------------
    def login(self, email="owner@test.local", password=PASSWORD, client=None):
        c = client or self.client
        r = c.post("/api/v1/auth/login", {"email": email, "password": password}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        c.cookies.clear()  # use the Bearer header only
        return r.json()

    def make_user(self, email, role, store=None):
        user = User.objects.create_user(email=email, password=PASSWORD, name=email.split("@")[0])
        StoreMember.objects.create(store=store or self.store, user=user, role=role)
        return user

    def client_for(self, email):
        c = APIClient()
        self.login(email=email, client=c)
        return c

    def checkout(self, items, customer=None, receipt=PNG, client=None, store_host=None, **payload):
        from django.core.files.uploadedfile import SimpleUploadedFile

        c = client or APIClient()
        data = {
            "data": json.dumps(
                {
                    "customer": customer
                    or {
                        "fullName": "خریدار",
                        "phone": "۰۹۱۲۱۲۳۴۵۶۷",
                        "province": "تهران",
                        "city": "تهران",
                        "address": "آدرس",
                        "postalCode": "1234567890",
                    },
                    "items": items,
                    **payload,
                }
            )
        }
        if receipt is not None:
            data["receipt"] = SimpleUploadedFile("r.png", receipt, content_type="image/png")
        extra = {"HTTP_ORIGIN": ORIGIN}
        if store_host:
            extra["HTTP_X_STORE_HOST"] = store_host
        return c.post("/api/v1/orders", data, format="multipart", **extra)

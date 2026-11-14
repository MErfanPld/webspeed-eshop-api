from .base import ApiTestCase


def block(bid, btype, **data):
    return {"id": bid, "type": btype, "data": data}


class PageTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.login()

    def create(self, slug, name="صفحه"):
        return self.client.post("/api/v1/admin/pages", {"name": name, "slug": slug}, format="json")

    def save(self, page, **changes):
        return self.client.put(f"/api/v1/admin/pages/{page['id']}", {"page": {**page, **changes}}, format="json")

    def test_slug_rules(self):
        self.assertEqual(self.create("/sale").json()["page"]["slug"], "/sale")
        r = self.create("/sale")
        self.assertEqual(r.status_code, 409)
        self.assertIn("قبلاً", r.json()["error"])
        for bad in ("/admin/x", "/cart", "/_layout/x", "/products/x", "/api/x"):
            r = self.create(bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("سیستمی", r.json()["error"])
        self.assertEqual(self.create("/درباره-ما").status_code, 201)
        self.assertEqual(self.create("x", name="").status_code, 400)

    def test_save_keeps_seo_and_sanitizes_urls(self):
        page = self.create("/seo").json()["page"]
        r = self.save(
            page,
            seo={"title": "T", "junk": 1},
            blocks=[block("b1", "button", label="x", href="javascript:alert(1)")],
        )
        self.assertEqual(r.status_code, 200, r.content)
        saved = r.json()["page"]
        self.assertEqual(saved["seo"], {"title": "T"})
        self.assertEqual(saved["blocks"][0]["data"]["href"], "#")

    def test_block_json_schema_validation(self):
        page = self.create("/v").json()["page"]
        r = self.save(page, blocks=[block("z", "evil")])
        self.assertEqual(r.status_code, 400)
        self.assertIn("ناشناخته", r.json()["error"])
        r = self.save(page, blocks=[block("h", "heading", text=123)])
        self.assertEqual(r.status_code, 400)
        r = self.save(page, blocks=[block("h", "heading", level=9)])
        self.assertEqual(r.status_code, 400)
        r = self.save(page, blocks=[block("t", "text", children=[])])
        self.assertEqual(r.status_code, 400)  # not a container

    def test_nesting_depth_limit(self):
        page = self.create("/deep").json()["page"]
        leaf = block("t", "text", text="x")
        tree = leaf
        for i in range(4):
            tree = block(f"s{i}", "section", children=[tree])
        self.assertEqual(self.save(page, blocks=[tree]).status_code, 200)
        tree = block("s9", "section", children=[tree])
        self.assertEqual(self.save(page, blocks=[tree]).status_code, 400)

    def test_draft_does_not_change_published_snapshot(self):
        page = self.create("/pub").json()["page"]
        self.save(page, blocks=[block("t", "text", text="v1")])
        self.client.post(f"/api/v1/admin/pages/{page['id']}/publish")
        draft = self.client.get(f"/api/v1/admin/pages/{page['id']}").json()["page"]
        self.save(draft, status="draft", publishedBlocks=[], blocks=[block("t", "text", text="v2")])
        pub = self.client.get("/api/v1/pages?slug=/pub").json()["page"]
        self.assertEqual(pub["publishedBlocks"][0]["data"]["text"], "v1")
        self.assertEqual(pub["blocks"], [])  # draft never exposed publicly
        self.client.post(f"/api/v1/admin/pages/{page['id']}/unpublish")
        self.assertEqual(self.client.get("/api/v1/pages?slug=/pub").status_code, 404)

    def test_layout_documents_not_routable(self):
        self.client.post("/api/v1/admin/pages/site-header/publish")
        self.assertEqual(self.client.get("/api/v1/pages?slug=/_layout/header").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/pages?id=site-header").status_code, 200)

    def test_duplicate_and_protected(self):
        a = self.client.post("/api/v1/admin/pages/home/duplicate").json()["page"]
        b = self.client.post("/api/v1/admin/pages/home/duplicate").json()["page"]
        self.assertEqual((a["slug"], b["slug"], a["type"]), ("/home-copy", "/home-copy-2", "landing"))
        self.assertNotEqual(a["blocks"][0]["id"], b["blocks"][0]["id"])
        self.assertEqual(self.client.delete("/api/v1/admin/pages/home").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/admin/pages/site-header/duplicate").status_code, 400)

    def test_home_slug_and_type_are_fixed(self):
        home = self.client.get("/api/v1/admin/pages/home").json()["page"]
        r = self.save(home, slug="/other", type="custom")
        self.assertEqual(r.json()["page"]["slug"], "/")
        self.assertEqual(r.json()["page"]["type"], "home")

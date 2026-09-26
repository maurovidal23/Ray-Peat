import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from peat_product_scorer.models import Product
from peat_product_scorer.web_app import _normalize_product_url, app


class WebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_score_endpoint_accepts_product_payload(self) -> None:
        response = self.client.post(
            "/api/score",
            json={
                "product": {
                    "name": "Aceite de girasol test",
                    "source": "Manual",
                    "ingredients": "Aceite refinado de girasol",
                    "nutrition": {"grasas": "100 g"},
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["band"], "avoid")
        self.assertEqual(data["product"]["nutrition_per_100g"]["fat_g"], 100.0)
        self.assertEqual(data["product"]["raw"], {})

    def test_score_endpoint_rejects_malformed_product_fields(self) -> None:
        invalid_products = [
            {"name": "Test", "ingredients": {"unexpected": "object"}},
            {"name": "Test", "ingredients": ["valid", 123]},
            {"name": "Test", "nutrition": ["fat", "10 g"]},
            {"name": "Test", "nutrition": {"fat": {"amount": 10}}},
            {"name": "Test", "nutrition": {"fat": True}},
            {"name": "Test", "url": "not a URL"},
        ]

        for product in invalid_products:
            with self.subTest(product=product):
                response = self.client.post("/api/score", json={"product": product})
                self.assertEqual(response.status_code, 422)

    def test_score_endpoint_enforces_product_bounds(self) -> None:
        responses = [
            self.client.post("/api/score", json={"product": {"name": "x" * 201}}),
            self.client.post(
                "/api/score",
                json={"product": {"name": "Test", "ingredients": ["x"] * 101}},
            ),
            self.client.post(
                "/api/score",
                json={"product": {"name": "Test", "nutrition": {f"n{i}": i for i in range(65)}}},
            ),
        ]

        self.assertTrue(all(response.status_code == 422 for response in responses))

    def test_score_endpoint_rejects_oversized_body(self) -> None:
        response = self.client.post(
            "/api/score",
            content=b"x" * (64 * 1024 + 1),
            headers={"content-type": "application/json"},
        )

        self.assertEqual(response.status_code, 413)

    def test_score_endpoint_requires_exactly_one_input(self) -> None:
        missing = self.client.post("/api/score", json={})
        both = self.client.post(
            "/api/score",
            json={"url": "https://www.dia.es/p/1", "product": {"name": "Test"}},
        )

        self.assertEqual(missing.status_code, 422)
        self.assertEqual(both.status_code, 422)

    def test_normalizes_bare_product_urls(self) -> None:
        self.assertEqual(
            _normalize_product_url("www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"),
            "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6",
        )
        self.assertEqual(
            _normalize_product_url(" https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6 "),
            "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6",
        )

    def test_score_endpoint_accepts_dia_url_payload(self) -> None:
        url = "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"
        product = Product(
            name="Leche entera Dia Lactea pack 6 x 1 L",
            source="DIA",
            url=url,
            brand="Dia Lactea",
            ingredient_text="Leche entera de vaca",
            ingredient_source="dia.ingredients.text",
            ingredients=["Leche entera de vaca"],
            nutrition_per_100g={"energy_kcal": 63.0, "fat_g": 3.6},
            missing_fields=[],
        )

        with patch("peat_product_scorer.web_app.fetch_product", return_value=product) as fetch_mock:
            response = self.client.post("/api/score", json={"url": url.replace("https://", "")})

        self.assertEqual(response.status_code, 200)
        fetch_mock.assert_called_once_with(url)
        data = response.json()
        self.assertEqual(data["product"]["source"], "DIA")
        self.assertEqual(data["product"]["missing_fields"], [])

    def test_score_endpoint_accepts_exact_and_subdomain_supermarket_hosts(self) -> None:
        urls = [
            "https://dia.es/p/1",
            "https://www.dia.es/p/1",
            "https://tienda.consum.es/es/p/1",
            "https://www.compraonline.alcampo.es/products/1",
        ]
        product = Product(name="Test", ingredients=[], nutrition_per_100g={})

        with patch("peat_product_scorer.web_app.fetch_product", return_value=product) as fetch_mock:
            for url in urls:
                with self.subTest(url=url):
                    response = self.client.post("/api/score", json={"url": url})
                    self.assertEqual(response.status_code, 200)

        self.assertEqual(fetch_mock.call_count, len(urls))

    def test_score_endpoint_rejects_ssrf_urls_before_fetch(self) -> None:
        urls = [
            "http://127.0.0.1/admin",
            "http://[::1]/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.4/internal",
            "file:///etc/passwd",
            "ftp://www.dia.es/file",
            "https://evil.example/?next=dia.es",
            "https://dia.es.evil.example/p/1",
            "https://evil-dia.es/p/1",
            "https://user:password@www.dia.es/p/1",
            "https://www.dia.es:8443/p/1",
        ]

        with patch("peat_product_scorer.web_app.fetch_product") as fetch_mock:
            for url in urls:
                with self.subTest(url=url):
                    response = self.client.post("/api/score", json={"url": url})
                    self.assertEqual(response.status_code, 422)

        fetch_mock.assert_not_called()

    def test_score_endpoint_allows_only_standard_explicit_ports(self) -> None:
        product = Product(name="Test", ingredients=[], nutrition_per_100g={})
        urls = ["http://www.dia.es:80/p/1", "https://www.dia.es:443/p/1"]

        with patch("peat_product_scorer.web_app.fetch_product", return_value=product) as fetch_mock:
            for url in urls:
                response = self.client.post("/api/score", json={"url": url})
                self.assertEqual(response.status_code, 200)

        self.assertEqual(fetch_mock.call_count, len(urls))

    def test_search_provider_options_endpoint(self) -> None:
        response = self.client.get("/api/search-providers")

        self.assertEqual(response.status_code, 200)
        providers = response.json()["providers"]
        self.assertIn("all", providers)
        self.assertIn("Mercadona", providers)
        self.assertIn("Alcampo", providers)
        self.assertIn("Eroski", providers)
        self.assertNotIn("Carrefour Espana", providers)

    def test_search_endpoint_passes_selected_provider(self) -> None:
        with patch("peat_product_scorer.web_app.search_products", return_value=[]) as search_mock:
            response = self.client.post(
                "/api/search",
                json={"q": "leche", "max_results": 5, "provider": "Alcampo"},
            )

        self.assertEqual(response.status_code, 200)
        search_mock.assert_called_once_with("leche", max_results=5, providers=["Alcampo"])
        self.assertEqual(response.json()["provider"], "Alcampo")

    def test_search_endpoints_reject_excessive_result_counts(self) -> None:
        for endpoint in ("/api/search", "/api/search-score"):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json={"q": "leche", "max_results": 21})
                self.assertEqual(response.status_code, 422)

    def test_search_endpoints_reject_work_when_capacity_is_exhausted(self) -> None:
        for endpoint in ("/api/search", "/api/search-score"):
            with (
                self.subTest(endpoint=endpoint),
                patch("peat_product_scorer.web_app.SEARCH_REQUEST_SLOTS") as slots,
            ):
                slots.acquire.return_value = False
                response = self.client.post(endpoint, json={"q": "leche"})

                self.assertEqual(response.status_code, 429)
                slots.release.assert_not_called()

    def test_products_page_contains_static_provider_options(self) -> None:
        response = self.client.get("/products")

        self.assertEqual(response.status_code, 200)
        self.assertIn("bestProductsProvider", response.text)
        self.assertIn('option value="Mercadona"', response.text)
        self.assertIn('option value="Alcampo"', response.text)
        self.assertIn('option value="Eroski"', response.text)
        self.assertNotIn('option value="Carrefour Espana"', response.text)

    def test_articles_endpoint_lists_pdf_derived_papers(self) -> None:
        response = self.client.get("/api/articles")

        self.assertEqual(response.status_code, 200)
        articles = response.json()["articles"]
        self.assertGreater(len(articles), 50)
        self.assertIn("languages", articles[0])
        self.assertIn("default_language", articles[0])
        self.assertNotIn("paragraphs", articles[0])

    def test_article_detail_endpoint_returns_selected_language_paragraphs(self) -> None:
        articles = self.client.get("/api/articles").json()["articles"]
        article_summary = articles[0]
        response = self.client.get(
            f"/api/articles/{article_summary['id']}?lang={article_summary['default_language']}"
        )

        self.assertEqual(response.status_code, 200)
        article = response.json()
        self.assertGreater(len(article["paragraphs"]), 1)
        self.assertEqual(article["id"], article_summary["id"])
        self.assertIn("source_pdf", article)

    def test_article_page_route_serves_reference_library(self) -> None:
        response = self.client.get("/articles/example-paper")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Ray Peat — Essays &amp; Articles", response.text)

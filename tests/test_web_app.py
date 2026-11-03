import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from peat_product_scorer.models import Product, SearchResult
from peat_product_scorer.supermarkets.contract import ProviderEvidenceError
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

    def test_score_endpoint_rejects_incomplete_provider_payload(self) -> None:
        response = self.client.post(
            "/api/score",
            json={
                "product": {
                    "name": "Leche incompleta",
                    "source": "DIA",
                    "url": "https://www.dia.es/p/1",
                    "ingredients": "leche",
                    "nutrition": {"grasas": "3 g"},
                }
            },
        )

        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertNotIn("score", data)
        self.assertIn("evidence incomplete", data["detail"])

    def test_score_endpoint_accepts_provider_payload_with_complete_evidence(self) -> None:
        response = self.client.post(
            "/api/score",
            json={
                "product": {
                    "name": "Leche entera",
                    "source": "DIA",
                    "url": "https://www.dia.es/p/1",
                    "ingredients": "leche entera",
                    "nutrition": {
                        "azucares": "4.7 g",
                        "proteinas": "3.1 g",
                        "grasas": "3.6 g",
                        "sal": "0.1 g",
                    },
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("score", response.json())

    def test_source_named_provider_payload_requires_complete_evidence(self) -> None:
        response = self.client.post(
            "/api/score",
            json={
                "product": {
                    "name": "Leche incompleta",
                    "source": "DIA",
                    "ingredients": "leche",
                    "nutrition": {"grasas": "3 g"},
                }
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("evidence incomplete", response.json()["detail"])

    def test_source_named_provider_payload_with_complete_evidence_scores(self) -> None:
        response = self.client.post(
            "/api/score",
            json={
                "product": {
                    "name": "Leche entera",
                    "source": "DIA",
                    "ingredients": "leche entera",
                    "nutrition": {
                        "azucares": "4.7 g",
                        "proteinas": "3.1 g",
                        "grasas": "3.6 g",
                        "sal": "0.1 g",
                    },
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("score", response.json())

    def test_dia_guardrail_error_stays_unscored_after_client_enrichment(self) -> None:
        incomplete = SearchResult(
            source="DIA",
            query="leche",
            display_name="Leche incompleta",
            product_id="incomplete",
            url="https://www.dia.es/p/incomplete",
        )

        def fetch(url: str, timeout: int = 10) -> Product:
            raise ProviderEvidenceError("DIA evidence incomplete: missing salt_g.")

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=[incomplete]),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            search_response = self.client.post(
                "/api/search-score",
                json={"q": "leche", "max_results": 5},
            )

        self.assertEqual(search_response.status_code, 200)
        self.assertNotIn("score", search_response.json()["results"][0])

        # The DIA browser enrichment posts the provider payload back to /api/score.
        enrichment_response = self.client.post(
            "/api/score",
            json={
                "product": {
                    "name": "Leche incompleta",
                    "source": "DIA",
                    "url": "https://www.dia.es/p/incomplete",
                    "ingredients": "leche",
                    "nutrition": {"grasas": "3 g"},
                }
            },
        )

        self.assertEqual(enrichment_response.status_code, 422)
        self.assertNotIn("score", enrichment_response.json())

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

    def test_score_endpoint_does_not_return_a_score_for_incomplete_evidence(self) -> None:
        with patch(
            "peat_product_scorer.web_app.fetch_product",
            side_effect=ProviderEvidenceError(
                "DIA evidence incomplete: missing salt_g.",
                missing=("salt_g",),
            ),
        ):
            response = self.client.post(
                "/api/score",
                json={"url": "https://www.dia.es/p/608P6"},
            )

        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertNotIn("score", data)
        self.assertIn("evidence incomplete", data["detail"])

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

    def test_connectors_endpoint_lists_only_conforming_providers(self) -> None:
        response = self.client.get("/api/connectors")

        self.assertEqual(response.status_code, 200)
        connectors = response.json()["connectors"]
        self.assertEqual(
            [connector["name"] for connector in connectors],
            ["Mercadona", "DIA", "Alcampo", "Consum", "Eroski", "Open Food Facts"],
        )
        self.assertNotIn("partial", response.text.lower())

    def test_search_provider_options_endpoint(self) -> None:
        response = self.client.get("/api/search-providers")

        self.assertEqual(response.status_code, 200)
        providers = response.json()["providers"]
        self.assertEqual(
            providers,
            ["all", "Mercadona", "DIA", "Alcampo", "Consum", "Eroski", "Open Food Facts"],
        )
        for removed_provider in ("Bon Preu / Esclat", "Esclat", "Carrefour Espana", "El Corte Ingles", "Lidl"):
            self.assertNotIn(removed_provider, providers)

    def test_search_endpoint_passes_selected_provider(self) -> None:
        with patch("peat_product_scorer.web_app.search_products", return_value=[]) as search_mock:
            response = self.client.post(
                "/api/search",
                json={"q": "leche", "max_results": 5, "provider": "Alcampo"},
            )

        self.assertEqual(response.status_code, 200)
        search_mock.assert_called_once_with("leche", max_results=5, providers=["Alcampo"])
        self.assertEqual(response.json()["provider"], "Alcampo")

    def test_search_score_endpoint_keeps_unscored_rows_last_without_a_score(self) -> None:
        incomplete = SearchResult(
            source="DIA",
            query="leche",
            display_name="Aaa leche incompleta",
            product_id="incomplete",
            url="https://www.dia.es/p/incomplete",
        )
        complete = SearchResult(
            source="DIA",
            query="leche",
            display_name="Zzz leche completa",
            product_id="complete",
            url="https://www.dia.es/p/complete",
        )
        complete_product = Product(
            name="Leche entera",
            ingredients=["leche entera"],
            nutrition_per_100g={
                "sugars_g": 4.7,
                "protein_g": 3.1,
                "fat_g": 3.6,
                "salt_g": 0.1,
            },
        )

        def fetch(url: str, timeout: int = 10) -> Product:
            if url.endswith("incomplete"):
                raise RuntimeError("evidence incomplete: missing salt_g")
            return complete_product

        with (
            patch(
                "peat_product_scorer.scorer.search_products",
                return_value=[incomplete, complete],
            ),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            response = self.client.post(
                "/api/search-score",
                json={"q": "leche", "max_results": 5},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(
            [result["search"]["product_id"] for result in data["results"]],
            ["complete", "incomplete"],
        )
        self.assertIn("score", data["results"][0])
        self.assertNotIn("score", data["results"][1])
        self.assertIn("evidence incomplete", data["results"][1]["error"])

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

    def test_products_page_populates_provider_options_dynamically(self) -> None:
        response = self.client.get("/products")

        self.assertEqual(response.status_code, 200)
        self.assertIn("bestProductsProvider", response.text)
        self.assertIn("/static/app.js", response.text)
        provider_select = re.search(
            r'<select id="bestProductsProvider"[^>]*>(?P<body>.*?)</select>',
            response.text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(provider_select)
        self.assertNotIn("<option", provider_select.group("body"))
        for removed_provider in ("Bon Preu / Esclat", "Esclat", "Carrefour Espana", "El Corte Ingles", "Lidl"):
            self.assertNotIn(removed_provider, response.text)

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

    def test_root_and_method_routes_serve_english_methodology(self) -> None:
        responses = [self.client.get(path) for path in ("/", "/method")]

        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertIn("How the score works.", response.text)
            self.assertIn('data-rule="dairy_positive"', response.text)
            self.assertIn('data-rule="calcium_phosphorus_positive"', response.text)
        self.assertEqual(responses[0].text, responses[1].text)

    def test_method_es_route_serves_spanish_methodology(self) -> None:
        response = self.client.get("/method-es")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="es">', response.text)
        self.assertIn("Cómo funciona la puntuación.", response.text)
        self.assertIn("Protección de proveedores", response.text)
        self.assertIn('data-rule="dairy_positive"', response.text)
        self.assertIn('data-rule="calcium_phosphorus_positive"', response.text)

    def test_method_pages_document_current_scoring_constants(self) -> None:
        for path in ("/", "/method", "/method-es"):
            response = self.client.get(path)
            with self.subTest(path=path):
                self.assertEqual(response.status_code, 200)
                for value in (
                    "30%",
                    "35%",
                    "15%",
                    "5%",
                    "80-100",
                    "65-79",
                    "45-64",
                    "25-44",
                    "0-24",
                    "evidence_quality",
                    "seed_oils_negative",
                ):
                    self.assertIn(value, response.text)
                for band in ("strong fit", "reasonable fit", "mixed", "weak fit", "avoid"):
                    self.assertIn(f'data-band="{band}"', response.text)
                self.assertEqual(response.text.count("data-rule="), 12)

    def test_method_pages_list_all_twelve_knowledge_base_rules(self) -> None:
        rule_ids = (
            "dairy_positive",
            "fruit_sugar_positive",
            "gelatin_collagen_positive",
            "seed_oils_negative",
            "soy_negative",
            "gums_negative",
            "phosphate_additives_negative",
            "fortified_iron_negative",
            "high_sugar_positive",
            "high_protein_positive",
            "high_fat_without_context_negative",
            "calcium_phosphorus_positive",
        )
        for path in ("/", "/method-es"):
            response = self.client.get(path)
            with self.subTest(path=path):
                for rule_id in rule_ids:
                    self.assertIn(f'data-rule="{rule_id}"', response.text)
                for delta in ("+14", "+10", "+8", "-24", "-14", "-12", "-10", "-12", "+6", "+5", "-7", "+12"):
                    self.assertIn(delta, response.text)

    def test_method_pages_define_the_provider_guardrail(self) -> None:
        english = self.client.get("/").text
        spanish = self.client.get("/method-es").text

        self.assertIn("Provider guardrail", english)
        self.assertIn("DIA", english)
        self.assertIn("Mercadona", english)
        self.assertIn("Protección de proveedores", spanish)
        self.assertIn("DIA", spanish)
        self.assertIn("Mercadona", spanish)

        from peat_product_scorer.supermarkets.fetcher import RELIABLE_SEARCH_PROVIDERS

        for path in ("/", "/method", "/method-es"):
            with self.subTest(path=path):
                page = self.client.get(path).text
                for provider in RELIABLE_SEARCH_PROVIDERS:
                    self.assertIn(f"<strong>{provider}</strong>", page)
        self.assertNotIn("Less reliable or generic providers are queried", english)
        self.assertNotIn("Los proveedores menos fiables o genéricos se consultan", spanish)
        self.assertIn("Non-conforming providers are not available", english)
        self.assertIn("Los proveedores que no cumplen los requisitos no están disponibles", spanish)

    def test_static_pages_share_topbar_and_omit_service_status(self) -> None:
        pages = {
            "/": "method",
            "/method": "method",
            "/method-es": "method",
            "/articles": "papers",
            "/articles-es": "papers",
        }
        for path, active in pages.items():
            response = self.client.get(path)
            with self.subTest(path=path):
                self.assertEqual(response.status_code, 200)
                self.assertIn('class="topbar app-header"', response.text)
                self.assertIn('class="topnav view-switcher"', response.text)
                for href in ('href="/articles"', 'href="/evaluator"', 'href="/products"', 'href="/"'):
                    self.assertIn(href, response.text)
                self.assertIn(f'class="view-button active" data-nav="{active}"', response.text)
                self.assertNotIn("serviceStatus", response.text)

    def test_app_pages_share_topbar_and_mark_active_view(self) -> None:
        for path, active in (("/evaluator", "evaluator"), ("/products", "best")):
            response = self.client.get(path)
            with self.subTest(path=path):
                self.assertEqual(response.status_code, 200)
                self.assertIn('class="topbar app-header"', response.text)
                self.assertIn('class="topnav view-switcher"', response.text)
                self.assertIn(f'class="view-button active" data-nav="{active}"', response.text)
                self.assertIn('id="serviceStatus"', response.text)

    def test_library_routes_keep_serving_english_and_spanish_pages(self) -> None:
        english = self.client.get("/articles")
        spanish = self.client.get("/articles-es")

        self.assertEqual(english.status_code, 200)
        self.assertEqual(spanish.status_code, 200)
        self.assertIn("The writings of", english.text)
        self.assertIn("Los escritos de", spanish.text)

import unittest
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

from peat_product_scorer.models import (
    Product,
    ProviderOutcome,
    ProviderSearchOutcome,
    ScoredSearchResults,
    SearchResult,
    SearchResults,
)
from peat_product_scorer.scorer import search_and_score
from peat_product_scorer.supermarkets.fetcher import (
    _search_dia_api,
    _search_generic_provider,
    _search_mercadona_categories,
    search_products,
)
from peat_product_scorer.supermarkets.openfoodfacts import OpenFoodFactsProvider
from peat_product_scorer.web_app import app


def _search_result(source: str = "DIA", index: int = 1) -> SearchResult:
    return SearchResult(
        source=source,
        query="leche",
        display_name=f"Leche {index}",
        product_id=str(index),
        url=f"https://www.dia.es/p/{index}",
    )


def _complete_product(name: str = "Leche entera") -> Product:
    return Product(
        name=name,
        ingredients=["leche entera"],
        nutrition_per_100g={
            "sugars_g": 4.7,
            "protein_g": 3.1,
            "fat_g": 3.6,
            "salt_g": 0.1,
        },
    )


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        payload: object = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.payload = payload
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class ProviderSearchOutcomeTests(unittest.TestCase):
    def test_generic_provider_http_403_is_blocked_with_cause(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            return_value=_FakeResponse(status_code=403),
        ):
            outcome = _search_generic_provider(
                "Alcampo",
                "https://www.compraonline.alcampo.es/search?text={query}",
                "compraonline.alcampo.es",
                "leche",
                5,
            )

        self.assertEqual(outcome.outcome, "blocked")
        self.assertEqual(outcome.products, 0)
        self.assertIn("HTTP 403", outcome.cause or "")
        self.assertEqual(list(outcome), [])

    def test_generic_provider_http_429_is_blocked_with_cause(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            return_value=_FakeResponse(status_code=429),
        ):
            outcome = _search_generic_provider(
                "Consum",
                "https://tienda.consum.es/es/search?text={query}",
                "tienda.consum.es",
                "leche",
                5,
            )

        self.assertEqual(outcome.outcome, "blocked")
        self.assertIn("HTTP 429", outcome.cause or "")

    def test_generic_provider_captcha_page_is_blocked_with_cause(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            return_value=_FakeResponse(text="<html>Please complete the CAPTCHA</html>"),
        ):
            outcome = _search_generic_provider(
                "Eroski",
                "https://supermercado.eroski.es/es/search/results/?q={query}",
                "supermercado.eroski.es",
                "leche",
                5,
            )

        self.assertEqual(outcome.outcome, "blocked")
        self.assertIn("captcha", (outcome.cause or "").lower())

    def test_generic_provider_exception_is_error_with_cause(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            side_effect=RuntimeError("network down"),
        ):
            outcome = _search_generic_provider(
                "Alcampo",
                "https://www.compraonline.alcampo.es/search?text={query}",
                "compraonline.alcampo.es",
                "leche",
                5,
            )

        self.assertEqual(outcome.outcome, "error")
        self.assertEqual(outcome.products, 0)
        self.assertIn("RuntimeError: network down", outcome.cause or "")

    def test_parsed_provider_without_products_is_empty(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            return_value=_FakeResponse(text="<html><body>No products here</body></html>"),
        ):
            outcome = _search_generic_provider(
                "Alcampo",
                "https://www.compraonline.alcampo.es/search?text={query}",
                "compraonline.alcampo.es",
                "leche",
                5,
            )

        self.assertEqual(outcome.outcome, "empty")
        self.assertEqual(outcome.products, 0)

    def test_dia_api_page_fallback_preserves_blocked_outcome(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            return_value=_FakeResponse(status_code=403),
        ):
            outcome = _search_dia_api("leche", 5)

        self.assertEqual(outcome.outcome, "blocked")
        self.assertIn("HTTP 403", outcome.cause or "")

    def test_mercadona_category_failure_is_surfaced_when_empty(self) -> None:
        category_list = {
            "results": [{"name": "Lacteos", "categories": [{"id": 12, "name": "Leche"}]}]
        }
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            side_effect=[
                _FakeResponse(payload=category_list),
                _FakeResponse(status_code=403),
            ],
        ):
            outcome = _search_mercadona_categories("leche", 5)

        self.assertEqual(outcome.outcome, "blocked")
        self.assertIn("HTTP 403", outcome.cause or "")

    def test_openfoodfacts_ok_counts_complete_evidence_products(self) -> None:
        payload = {
            "products": [
                {
                    "code": "123",
                    "product_name_es": "Leche entera",
                    "ingredients_text_es": "Leche entera de vaca",
                    "nutriments": {
                        "sugars_100g": 4.7,
                        "proteins_100g": 3.1,
                        "fat_100g": 3.6,
                        "salt_100g": 0.1,
                    },
                }
            ]
        }
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(payload=payload),
        ):
            outcome = OpenFoodFactsProvider().search("leche", max_results=5)

        self.assertEqual(outcome.outcome, "ok")
        self.assertEqual(outcome.products, 1)
        self.assertEqual(len(outcome), 1)

    def test_openfoodfacts_incomplete_products_are_empty(self) -> None:
        payload = {
            "products": [
                {
                    "code": "123",
                    "product_name_es": "Solo azucar",
                    "ingredients_text_es": "azucar",
                    "nutriments": {"sugars_100g": 99.0},
                }
            ]
        }
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(payload=payload),
        ):
            outcome = OpenFoodFactsProvider().search("azucar", max_results=5)

        self.assertEqual(outcome.outcome, "empty")
        self.assertEqual(outcome.products, 0)
        self.assertEqual(outcome, [])

    def test_search_products_aggregates_mixed_provider_outcomes(self) -> None:
        dia = _search_result("DIA", 1)
        outcomes = {
            "peat_product_scorer.supermarkets.fetcher._search_dia": ProviderSearchOutcome(
                [dia], provider="DIA", outcome="ok", products=1
            ),
            "peat_product_scorer.supermarkets.fetcher._search_mercadona_categories": ProviderSearchOutcome(
                [], provider="Mercadona", outcome="blocked", products=0, cause="HTTP 403"
            ),
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider": ProviderSearchOutcome(
                [], provider="Alcampo", outcome="empty", products=0
            ),
            "peat_product_scorer.supermarkets.fetcher._search_openfoodfacts": ProviderSearchOutcome(
                [], provider="Open Food Facts", outcome="error", products=0, cause="RuntimeError: boom"
            ),
        }
        with (
            patch(
                "peat_product_scorer.supermarkets.fetcher._search_dia",
                return_value=outcomes["peat_product_scorer.supermarkets.fetcher._search_dia"],
            ),
            patch(
                "peat_product_scorer.supermarkets.fetcher._search_mercadona_categories",
                return_value=outcomes["peat_product_scorer.supermarkets.fetcher._search_mercadona_categories"],
            ),
            patch(
                "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
                return_value=outcomes["peat_product_scorer.supermarkets.fetcher._search_generic_provider"],
            ),
            patch(
                "peat_product_scorer.supermarkets.fetcher._search_openfoodfacts",
                return_value=outcomes["peat_product_scorer.supermarkets.fetcher._search_openfoodfacts"],
            ),
        ):
            results = search_products(
                "leche",
                max_results=5,
                providers=["DIA", "Mercadona", "Alcampo", "Open Food Facts"],
            )

        self.assertEqual(results, [dia])
        self.assertEqual(
            [status.provider for status in results.provider_status],
            ["DIA", "Mercadona", "Alcampo", "Open Food Facts"],
        )
        statuses = {status.provider: status.to_dict() for status in results.provider_status}
        self.assertEqual(statuses["DIA"], {"provider": "DIA", "outcome": "ok", "products": 1})
        self.assertEqual(
            statuses["Mercadona"],
            {"provider": "Mercadona", "outcome": "blocked", "products": 0, "cause": "HTTP 403"},
        )
        self.assertEqual(statuses["Alcampo"], {"provider": "Alcampo", "outcome": "empty", "products": 0})
        self.assertEqual(statuses["Open Food Facts"]["outcome"], "error")
        self.assertIn("RuntimeError: boom", statuses["Open Food Facts"]["cause"])

    def test_search_and_score_reports_complete_evidence_count(self) -> None:
        incomplete = _search_result("DIA", 1)
        complete = _search_result("DIA", 2)
        search_outcome = SearchResults(
            [incomplete, complete],
            provider_status=[ProviderOutcome("DIA", "ok", 2)],
        )

        def fetch(url: str, timeout: int = 10) -> Product:
            if url.endswith("1"):
                raise RuntimeError("missing evidence")
            return _complete_product()

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=search_outcome),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            results = search_and_score("leche", providers=["DIA"])

        self.assertEqual(results.provider_status[0].outcome, "ok")
        self.assertEqual(results.provider_status[0].products, 1)

    def test_search_and_score_keeps_blocked_search_outcome(self) -> None:
        blocked = SearchResults(
            [],
            provider_status=[ProviderOutcome("Mercadona", "blocked", 0, "HTTP 403")],
        )

        with patch("peat_product_scorer.scorer.search_products", return_value=blocked):
            results = search_and_score("leche", providers=["Mercadona"])

        self.assertEqual(results, [])
        self.assertEqual(
            results.provider_status[0].to_dict(),
            {
                "provider": "Mercadona",
                "outcome": "blocked",
                "products": 0,
                "cause": "HTTP 403",
            },
        )


class ProviderStatusApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_search_endpoint_includes_provider_status(self) -> None:
        statuses = [
            ProviderOutcome("DIA", "ok", 10),
            ProviderOutcome("Mercadona", "blocked", 0, "HTTP 403"),
        ]
        with patch(
            "peat_product_scorer.web_app.search_products",
            return_value=SearchResults([], provider_status=statuses),
        ):
            response = self.client.post(
                "/api/search",
                json={"q": "leche", "max_results": 5},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["provider_status"],
            [
                {"provider": "DIA", "outcome": "ok", "products": 10},
                {
                    "provider": "Mercadona",
                    "outcome": "blocked",
                    "products": 0,
                    "cause": "HTTP 403",
                },
            ],
        )

    def test_search_score_endpoints_include_provider_status(self) -> None:
        statuses = [
            ProviderOutcome("DIA", "ok", 10),
            ProviderOutcome("Mercadona", "blocked", 0, "HTTP 403"),
        ]
        scored = ScoredSearchResults([], provider_status=statuses)
        with patch("peat_product_scorer.web_app.search_and_score", return_value=scored):
            for endpoint in ("/api/search-score", "/api/search-and-score"):
                with self.subTest(endpoint=endpoint):
                    response = self.client.post(
                        endpoint,
                        json={"q": "leche", "max_results": 5},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.json()["provider_status"],
                        [
                            {"provider": "DIA", "outcome": "ok", "products": 10},
                            {
                                "provider": "Mercadona",
                                "outcome": "blocked",
                                "products": 0,
                                "cause": "HTTP 403",
                            },
                        ],
                    )


if __name__ == "__main__":
    unittest.main()

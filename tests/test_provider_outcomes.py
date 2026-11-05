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
    _search_generic_provider,
    search_products,
)
from peat_product_scorer.web_app import app


def _search_result(source: str = "Eroski", index: int = 1) -> SearchResult:
    return SearchResult(
        source=source,
        query="leche",
        display_name=f"Leche {index}",
        product_id=str(index),
        url=f"https://supermercado.eroski.es/productdetail/{index}",
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
    def test_generic_provider_cdn_references_do_not_discard_products(self) -> None:
        for cdn in (
            "https://cdnjs.cloudflare.com/ajax/libs/example.js",
            "https://static.cloudflareinsights.com/beacon.min.js",
            "https://example.akamaized.net/assets/shop.js",
            "https://www.akamai.com/assets/shop.js",
        ):
            with self.subTest(cdn=cdn), patch(
                "peat_product_scorer.supermarkets.fetcher.requests.get",
                return_value=_FakeResponse(text=(
                    f'<html><script src="{cdn}"></script>'
                    '<a href="/es/productdetail/leche-entera/12345">Leche entera</a></html>'
                )),
            ):
                outcome = _search_generic_provider(
                    "Eroski",
                    "https://supermercado.eroski.es/es/search/results/?q={query}",
                    "supermercado.eroski.es", "leche", 5,
                )
                self.assertEqual(outcome.outcome, "ok")
                self.assertEqual(len(outcome), 1)
                self.assertIsNone(outcome.cause)

    def test_generic_provider_cloudflare_challenge_is_blocked(self) -> None:
        for challenge in (
            '<script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>',
            '<script>window._cf_chl_opt = {};</script>',
        ):
            with self.subTest(challenge=challenge), patch(
                "peat_product_scorer.supermarkets.fetcher.requests.get",
                return_value=_FakeResponse(text=f"<html>{challenge}</html>"),
            ):
                outcome = _search_generic_provider(
                    "Eroski",
                    "https://supermercado.eroski.es/es/search/results/?q={query}",
                    "supermercado.eroski.es", "leche", 5,
                )
                self.assertEqual(outcome.outcome, "blocked")
                self.assertEqual(outcome.products, 0)
                self.assertTrue(outcome.cause)

    def test_generic_provider_http_403_is_blocked_with_cause(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher.requests.get",
            return_value=_FakeResponse(status_code=403),
        ):
            outcome = _search_generic_provider(
                "Eroski",
                "https://supermercado.eroski.es/es/search/results/?q={query}",
                "supermercado.eroski.es",
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
                "Eroski",
                "https://supermercado.eroski.es/es/search/results/?q={query}",
                "supermercado.eroski.es",
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
                "Eroski",
                "https://supermercado.eroski.es/es/search/results/?q={query}",
                "supermercado.eroski.es",
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
                "Eroski",
                "https://supermercado.eroski.es/es/search/results/?q={query}",
                "supermercado.eroski.es",
                "leche",
                5,
            )

        self.assertEqual(outcome.outcome, "empty")
        self.assertEqual(outcome.products, 0)

    def test_search_products_aggregates_provider_outcomes(self) -> None:
        eroski = _search_result("Eroski", 1)
        outcome = ProviderSearchOutcome(
            [eroski], provider="Eroski", outcome="ok", products=1
        )
        with patch(
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
            return_value=outcome,
        ):
            results = search_products("leche", max_results=5, providers=["Eroski"])

        self.assertEqual(results, [eroski])
        self.assertEqual(
            [status.provider for status in results.provider_status],
            ["Eroski"],
        )
        statuses = {status.provider: status.to_dict() for status in results.provider_status}
        self.assertEqual(statuses["Eroski"], {"provider": "Eroski", "outcome": "ok", "products": 1})

    def test_search_products_keeps_blocked_outcome(self) -> None:
        blocked = ProviderSearchOutcome(
            [], provider="Eroski", outcome="blocked", products=0, cause="HTTP 403"
        )
        with patch(
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
            return_value=blocked,
        ):
            results = search_products("leche", max_results=5, providers=["Eroski"])

        self.assertEqual(results, [])
        self.assertEqual(
            results.provider_status[0].to_dict(),
            {
                "provider": "Eroski",
                "outcome": "blocked",
                "products": 0,
                "cause": "HTTP 403",
            },
        )

    def test_search_and_score_reports_complete_evidence_count(self) -> None:
        incomplete = _search_result("Eroski", 1)
        complete = _search_result("Eroski", 2)
        search_outcome = SearchResults(
            [incomplete, complete],
            provider_status=[ProviderOutcome("Eroski", "ok", 2)],
        )

        def fetch(url: str, timeout: int = 10) -> Product:
            if url.endswith("1"):
                raise RuntimeError("missing evidence")
            return _complete_product()

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=search_outcome),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            results = search_and_score("leche", providers=["Eroski"])

        self.assertEqual(results.provider_status[0].outcome, "ok")
        self.assertEqual(results.provider_status[0].products, 1)

    def test_search_and_score_keeps_blocked_search_outcome(self) -> None:
        blocked = SearchResults(
            [],
            provider_status=[ProviderOutcome("Eroski", "blocked", 0, "HTTP 403")],
        )

        with patch("peat_product_scorer.scorer.search_products", return_value=blocked):
            results = search_and_score("leche", providers=["Eroski"])

        self.assertEqual(results, [])
        self.assertEqual(
            results.provider_status[0].to_dict(),
            {
                "provider": "Eroski",
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
            ProviderOutcome("Eroski", "ok", 10),
            ProviderOutcome("Manual", "blocked", 0, "HTTP 403"),
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
                {"provider": "Eroski", "outcome": "ok", "products": 10},
                {
                    "provider": "Manual",
                    "outcome": "blocked",
                    "products": 0,
                    "cause": "HTTP 403",
                },
            ],
        )

    def test_search_score_endpoints_include_provider_status(self) -> None:
        statuses = [
            ProviderOutcome("Eroski", "ok", 10),
            ProviderOutcome("Manual", "blocked", 0, "HTTP 403"),
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
                            {"provider": "Eroski", "outcome": "ok", "products": 10},
                            {
                                "provider": "Manual",
                                "outcome": "blocked",
                                "products": 0,
                                "cause": "HTTP 403",
                            },
                        ],
                    )


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

from peat_product_scorer.models import Product
from peat_product_scorer.supermarkets.adapters import ADAPTERS, SUPPORTED_DOMAINS
from peat_product_scorer.supermarkets.contract import (
    GUARDRAIL_NUTRIENT_KEYS,
    ProviderEvidenceError,
)
from peat_product_scorer.supermarkets.openfoodfacts import (
    HEADERS,
    SOURCE,
    USER_AGENT,
    OpenFoodFactsProvider,
    product_url,
)
from peat_product_scorer.web_app import _normalize_product_url, app


def _nutriments() -> dict[str, object]:
    return {
        "sugars_100g": 4.7,
        "proteins_100g": 3.1,
        "fat_100g": 3.6,
        "saturated-fat_100g": 2.3,
        "salt_100g": 0.1,
        "carbohydrates_100g": 4.8,
        "fiber_100g": 0.0,
        "calcium_100g": 0.12,
        "phosphorus_100g": 0.09,
    }


def _conforming_product(code: str = "1234567890123") -> dict[str, object]:
    return {
        "code": code,
        "product_name_es": "Leche entera",
        "brands": "Marca",
        "categories_tags": ["en:dairies", "en:milks"],
        "ingredients_text_es": "Leche entera de vaca, sal",
        "nutriments": _nutriments(),
    }


class _FakeResponse:
    def __init__(
        self,
        payload: object = None,
        *,
        status_code: int = 200,
        json_error: Exception | None = None,
        http_error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error
        self.http_error = http_error

    def raise_for_status(self) -> None:
        if self.http_error is not None:
            raise self.http_error

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class OpenFoodFactsSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenFoodFactsProvider()

    def test_search_maps_conforming_products_and_drops_incomplete_ones(self) -> None:
        payload = {
            "products": [
                _conforming_product(),
                {
                    "code": "999",
                    "product_name_es": "Producto incompleto",
                    "nutriments": {"sugars_100g": 1.0},
                },
                {"product_name_es": "Sin codigo"},
            ]
        }
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(payload),
        ) as get_mock:
            results = self.provider.search("leche", max_results=10)

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.source, SOURCE)
        self.assertEqual(result.product_id, "1234567890123")
        self.assertEqual(result.url, product_url("1234567890123"))
        self.assertEqual(result.display_name, "Leche entera")
        self.assertEqual(result.brand, "Marca")
        self.assertEqual(result.query, "leche")

        _, kwargs = get_mock.call_args
        self.assertEqual(kwargs["params"]["search_terms"], "leche")
        self.assertEqual(kwargs["params"]["countries_tags_en"], "spain")
        self.assertEqual(kwargs["headers"]["User-Agent"], USER_AGENT)

    def test_search_uses_an_explicit_identifying_user_agent(self) -> None:
        self.assertIn("Ray-Peat", HEADERS["User-Agent"])
        self.assertNotIn("Mozilla", HEADERS["User-Agent"])

    def test_search_drops_products_that_fail_the_guardrail(self) -> None:
        incomplete = {
            "code": "42",
            "product_name_es": "Solo azucar",
            "ingredients_text_es": "azucar",
            "nutriments": {"sugars_100g": 99.0},
        }
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse({"products": [incomplete]}),
        ):
            results = self.provider.search("azucar", max_results=5)

        self.assertEqual(results, [])

    def test_search_returns_empty_on_http_error(self) -> None:
        error = requests.HTTPError("unavailable")
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(http_error=error),
        ):
            self.assertEqual(self.provider.search("leche"), [])

    def test_search_returns_empty_on_malformed_json(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(json_error=ValueError("bad json")),
        ):
            self.assertEqual(self.provider.search("leche"), [])

    def test_search_returns_empty_for_malformed_payload(self) -> None:
        for payload in (None, [], {"products": "not-a-list"}, {"products": ["bad"]}):
            with (
                self.subTest(payload=payload),
                patch(
                    "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
                    return_value=_FakeResponse(payload),
                ),
            ):
                self.assertEqual(self.provider.search("leche"), [])


class OpenFoodFactsFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = OpenFoodFactsProvider()
        self.url = "https://world.openfoodfacts.org/product/1234567890123"

    def test_fetch_maps_ingredients_and_all_nutriments(self) -> None:
        payload = {"status": 1, "product": _conforming_product()}
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(payload),
        ) as get_mock:
            product = self.provider.fetch(self.url, timeout=7)

        self.assertEqual(product.source, SOURCE)
        self.assertEqual(str(product.url), self.url)
        self.assertEqual(product.name, "Leche entera")
        self.assertEqual(product.ingredients, ["Leche entera de vaca", "sal"])
        self.assertEqual(product.ingredient_source, "openfoodfacts.ingredients_text_es")
        self.assertEqual(product.missing_fields, [])
        self.assertEqual(
            product.nutrition_per_100g,
            {
                "sugars_g": 4.7,
                "protein_g": 3.1,
                "fat_g": 3.6,
                "saturated_fat_g": 2.3,
                "salt_g": 0.1,
                "carbohydrate_g": 4.8,
                "carbs_g": 4.8,
                "fiber_g": 0.0,
                "calcium_mg": 0.12,
                "phosphorus_mg": 0.09,
            },
        )
        _, kwargs = get_mock.call_args
        self.assertEqual(kwargs["headers"]["User-Agent"], USER_AGENT)
        self.assertEqual(kwargs["timeout"], 7)

    def test_fetch_reports_missing_ingredients_and_nutrition_without_defaults(self) -> None:
        payload = {
            "status": 1,
            "product": {"code": "1234567890123", "product_name_es": "Producto vacio"},
        }
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(payload),
        ):
            product = self.provider.fetch(self.url)

        self.assertEqual(product.ingredients, [])
        self.assertIsNone(product.ingredient_text)
        self.assertIsNone(product.ingredient_source)
        self.assertEqual(product.nutrition_per_100g, {})
        self.assertEqual(product.missing_fields, ["ingredients", "nutrition_per_100g"])

    def test_fetch_omits_non_numeric_nutriments(self) -> None:
        product_payload = _conforming_product()
        product_payload["nutriments"] = {
            "sugars_100g": "4,7",
            "proteins_100g": "not a number",
            "fat_100g": True,
            "salt_100g": float("nan"),
        }
        payload = {"status": 1, "product": product_payload}
        with patch(
            "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
            return_value=_FakeResponse(payload),
        ):
            product = self.provider.fetch(self.url)

        self.assertEqual(product.nutrition_per_100g, {"sugars_g": 4.7})

    def test_fetch_and_validate_rejects_guardrail_failures(self) -> None:
        payload = {
            "status": 1,
            "product": {
                "code": "1234567890123",
                "product_name_es": "Producto incompleto",
                "ingredients_text_es": "leche",
                "nutriments": {"fat_100g": 3.0, "salt_100g": 0.1},
            },
        }
        with (
            patch(
                "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
                return_value=_FakeResponse(payload),
            ),
            self.assertRaises(ProviderEvidenceError) as context,
        ):
            self.provider.fetch_and_validate(self.url)

        self.assertTrue(set(context.exception.missing).issubset(set(GUARDRAIL_NUTRIENT_KEYS)))

    def test_fetch_rejects_urls_outside_provider_domains_before_request(self) -> None:
        with (
            patch("peat_product_scorer.supermarkets.openfoodfacts.requests.get") as get_mock,
            self.assertRaises(ValueError),
        ):
            self.provider.fetch("https://www.carrefour.es/supermercado/p/1")

        get_mock.assert_not_called()

    def test_fetch_requires_a_product_code(self) -> None:
        with (
            patch("peat_product_scorer.supermarkets.openfoodfacts.requests.get") as get_mock,
            self.assertRaises(ValueError),
        ):
            self.provider.fetch("https://world.openfoodfacts.org/")

        get_mock.assert_not_called()

    def test_fetch_raises_http_error_for_non_success_status(self) -> None:
        error = requests.HTTPError("server error")
        with (
            patch(
                "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
                return_value=_FakeResponse(http_error=error, status_code=500),
            ),
            self.assertRaises(requests.HTTPError),
        ):
            self.provider.fetch(self.url)

    def test_fetch_raises_evidence_error_for_malformed_json(self) -> None:
        with (
            patch(
                "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
                return_value=_FakeResponse(json_error=ValueError("bad json")),
            ),
            self.assertRaises(ProviderEvidenceError),
        ):
            self.provider.fetch(self.url)

    def test_fetch_raises_evidence_error_for_unavailable_or_missing_products(self) -> None:
        payloads = (
            {"status": 0},
            {"status": "0"},
            {"status": 1},
            {"status": 1, "product": None},
            {"status": 1, "product": {}},
            [],
        )
        for payload in payloads:
            with (
                self.subTest(payload=payload),
                patch(
                    "peat_product_scorer.supermarkets.openfoodfacts.requests.get",
                    return_value=_FakeResponse(payload),
                ),
                self.assertRaises(ProviderEvidenceError),
            ):
                self.provider.fetch(self.url)


class OpenFoodFactsRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_adapter_registered_for_openfoodfacts_domains(self) -> None:
        adapter = next(adapter for adapter in ADAPTERS if adapter.name == SOURCE)
        self.assertEqual(
            adapter.domains,
            ("openfoodfacts.org", "world.openfoodfacts.org"),
        )
        self.assertIn("openfoodfacts.org", SUPPORTED_DOMAINS)
        self.assertIn("world.openfoodfacts.org", SUPPORTED_DOMAINS)

    def test_connectors_endpoint_lists_openfoodfacts(self) -> None:
        response = self.client.get("/api/connectors")

        self.assertEqual(response.status_code, 200)
        connectors = {connector["name"]: connector for connector in response.json()["connectors"]}
        self.assertIn(SOURCE, connectors)
        self.assertEqual(
            connectors[SOURCE]["domains"],
            ["openfoodfacts.org", "world.openfoodfacts.org"],
        )

    def test_search_providers_endpoint_lists_openfoodfacts(self) -> None:
        response = self.client.get("/api/search-providers")

        self.assertEqual(response.status_code, 200)
        self.assertIn(SOURCE, response.json()["providers"])

    def test_product_urls_are_allowed_by_the_web_app_allowlist(self) -> None:
        self.assertEqual(
            _normalize_product_url("https://world.openfoodfacts.org/product/1234567890123"),
            "https://world.openfoodfacts.org/product/1234567890123",
        )


class OpenFoodFactsFetchDispatchTests(unittest.TestCase):
    def test_fetch_product_dispatches_openfoodfacts_urls(self) -> None:
        from peat_product_scorer.supermarkets import fetcher

        complete = Product(
            name="Leche entera",
            source=SOURCE,
            url="https://world.openfoodfacts.org/product/1234567890123",
            ingredients=["leche entera"],
            nutrition_per_100g={
                "sugars_g": 4.7,
                "protein_g": 3.1,
                "fat_g": 3.6,
                "salt_g": 0.1,
            },
        )
        with patch.object(
            fetcher,
            "_fetch_openfoodfacts_product",
            return_value=complete,
        ) as fetch_mock:
            result = fetcher.fetch_product(
                "https://world.openfoodfacts.org/product/1234567890123"
            )

        self.assertIs(result, complete)
        fetch_mock.assert_called_once_with(
            "https://world.openfoodfacts.org/product/1234567890123",
            timeout=20,
        )


if __name__ == "__main__":
    unittest.main()

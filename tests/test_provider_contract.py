import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from peat_product_scorer.cli import app as cli_app
from peat_product_scorer.models import Product, SearchResult
from peat_product_scorer.scorer import search_and_score
from peat_product_scorer.supermarkets import fetcher
from peat_product_scorer.supermarkets.contract import (
    GUARDRAIL_NUTRIENT_KEYS,
    EvidenceGuardrail,
    GuardrailResult,
    ProductProvider,
    ProviderEvidenceError,
    check_guardrail,
    require_evidence,
    validate_provider_url,
)


def _product(*, nutrient_keys: tuple[str, ...], ingredients: list[str]) -> Product:
    nutrition = {key: float(index) for index, key in enumerate(nutrient_keys)}
    return Product(name="Test product", ingredients=ingredients, nutrition_per_100g=nutrition)


class GuardrailTests(unittest.TestCase):
    def test_guardrail_keys_are_exact(self) -> None:
        self.assertEqual(
            GUARDRAIL_NUTRIENT_KEYS,
            ("sugars_g", "protein_g", "fat_g", "saturated_fat_g", "salt_g", "carbs_g"),
        )

    def test_three_of_six_nutrients_fails(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:3], ingredients=["leche"])

        result = check_guardrail(product)

        self.assertIsInstance(result, GuardrailResult)
        self.assertFalse(result.ok)
        self.assertEqual(result.missing, GUARDRAIL_NUTRIENT_KEYS[3:])

    def test_four_of_six_nutrients_passes(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4], ingredients=["leche"])

        result = check_guardrail(product)

        self.assertTrue(result.ok)
        self.assertEqual(result.missing, GUARDRAIL_NUTRIENT_KEYS[4:])

    def test_empty_ingredients_fails_even_with_complete_nutrition(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS, ingredients=[])

        result = check_guardrail(product)

        self.assertFalse(result.ok)
        self.assertEqual(result.missing[0], "ingredients")

    def test_blank_ingredients_are_treated_as_missing(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS, ingredients=["   "])

        self.assertFalse(check_guardrail(product).ok)

    def test_non_finite_nutrients_are_treated_as_missing(self) -> None:
        product = Product(
            name="Test product",
            ingredients=["leche"],
            nutrition_per_100g={
                "sugars_g": float("nan"),
                "protein_g": float("inf"),
                "fat_g": 3.0,
                "saturated_fat_g": 2.0,
            },
        )

        result = check_guardrail(product)

        self.assertFalse(result.ok)
        self.assertIn("sugars_g", result.missing)
        self.assertIn("protein_g", result.missing)

    def test_custom_guardrail_thresholds_are_respected(self) -> None:
        guardrail = EvidenceGuardrail(
            nutrient_keys=("sugars_g", "protein_g"),
            min_nutrients=1,
        )
        product = _product(nutrient_keys=("sugars_g",), ingredients=["leche"])

        self.assertTrue(guardrail.check(product).ok)

    def test_carbohydrate_g_does_not_satisfy_carbs_guardrail_slot(self) -> None:
        product = Product(
            name="Test product",
            ingredients=["leche"],
            nutrition_per_100g={
                "sugars_g": 4.7,
                "protein_g": 3.1,
                "fat_g": 3.6,
                "carbohydrate_g": 4.8,
            },
        )

        result = check_guardrail(product)

        self.assertFalse(result.ok)
        self.assertIn("carbs_g", result.missing)
        self.assertEqual(result.missing, ("saturated_fat_g", "salt_g", "carbs_g"))

    def test_zero_nutrients_count_as_present_evidence(self) -> None:
        product = Product(
            name="Test product",
            ingredients=["leche"],
            nutrition_per_100g={
                "sugars_g": 0.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "salt_g": 0.0,
            },
        )

        self.assertTrue(check_guardrail(product).ok)

    def test_guardrail_is_immutable(self) -> None:
        guardrail = EvidenceGuardrail()

        with self.assertRaises(FrozenInstanceError):
            guardrail.min_nutrients = 2  # type: ignore[misc]


class RequireEvidenceTests(unittest.TestCase):
    def test_returns_product_when_evidence_is_complete(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4], ingredients=["leche"])

        self.assertIs(require_evidence(product), product)

    def test_raises_with_source_and_missing_nutrients(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:3], ingredients=["leche"])

        with self.assertRaises(ProviderEvidenceError) as context:
            require_evidence(product, source="DIA")

        self.assertEqual(
            str(context.exception),
            "DIA evidence incomplete: missing saturated_fat_g, salt_g, carbs_g.",
        )
        self.assertEqual(context.exception.missing, GUARDRAIL_NUTRIENT_KEYS[3:])


class UrlValidationTests(unittest.TestCase):
    def test_accepts_allowlisted_hosts_and_standard_ports(self) -> None:
        urls = (
            "https://dia.es/p/1",
            "https://www.dia.es/p/1",
            "http://www.dia.es:80/p/1",
            "https://www.dia.es:443/p/1",
            "https://www.dia.es./p/1",
        )

        for url in urls:
            with self.subTest(url=url):
                validate_provider_url(url, ("dia.es",))

    def test_rejects_unsafe_url_components(self) -> None:
        urls = (
            "ftp://www.dia.es/p/1",
            "https:///p/1",
            "https://user:password@www.dia.es/p/1",
            "https://www.dia.es:8443/p/1",
            "https://www.dia.es:not-a-port/p/1",
            "https://169.254.169.254/latest/meta-data/",
            "https://www.dia.es.attacker.example/p/1",
            "https://evil-dia.es/p/1",
            "https://www.carrefour.es/supermercado/p/1",
        )

        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_provider_url(url, ("dia.es",))


class ProviderContractTests(unittest.TestCase):
    def test_fetch_and_validate_returns_complete_product(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4], ingredients=["leche"])
        provider = _FakeProvider(product)

        self.assertIs(provider.fetch_and_validate("https://www.dia.es/p/1"), product)

    def test_fetch_and_validate_forwards_timeout(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4], ingredients=["leche"])
        provider = _FakeProvider(product)

        provider.fetch_and_validate("https://www.dia.es/p/1", timeout=7)

        self.assertEqual(provider.timeouts, [7])

    def test_fetch_and_validate_raises_for_incomplete_product(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:3], ingredients=["leche"])
        provider = _FakeProvider(product)

        with self.assertRaises(ProviderEvidenceError) as context:
            provider.fetch_and_validate("https://www.dia.es/p/1")

        message = str(context.exception)
        self.assertIn("Fake evidence incomplete", message)
        self.assertIn("saturated_fat_g", message)
        self.assertIn("salt_g", message)

    def test_fetch_and_validate_rejects_urls_outside_provider_domains(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4], ingredients=["leche"])
        provider = _FakeProvider(product)

        with self.assertRaises(ValueError):
            provider.fetch_and_validate("https://www.carrefour.es/supermercado/p/1")

        self.assertEqual(provider.timeouts, [])

    def test_fetch_and_validate_rejects_unsafe_urls_before_fetch(self) -> None:
        product = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4], ingredients=["leche"])
        urls = (
            "https://user:password@www.dia.es/p/1",
            "https://www.dia.es:8443/p/1",
            "https://169.254.169.254/latest/meta-data/",
            "https://www.dia.es.attacker.example/p/1",
        )

        for url in urls:
            with self.subTest(url=url):
                provider = _FakeProvider(product)
                with self.assertRaises(ValueError):
                    provider.fetch_and_validate(url)
                self.assertEqual(provider.timeouts, [])

    def test_product_provider_is_abstract(self) -> None:
        with self.assertRaises(TypeError):
            ProductProvider()  # type: ignore[abstract]

    def test_provider_missing_required_methods_cannot_be_instantiated(self) -> None:
        class IncompleteProvider(ProductProvider):
            name = "Incomplete"
            domains = ("dia.es",)

            def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
                return []

        with self.assertRaises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]


class _FakeProvider(ProductProvider):
    name = "Fake"
    domains = ("dia.es",)

    def __init__(self, product: Product) -> None:
        self.product = product
        self.timeouts: list[int] = []

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        return []

    def fetch(self, url: str, timeout: int = 20) -> Product:
        self.timeouts.append(timeout)
        return self.product


class FetchProductGuardrailTests(unittest.TestCase):
    def test_fetch_product_raises_for_partial_product(self) -> None:
        partial = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:3], ingredients=["leche"])

        with (
            patch(
                "peat_product_scorer.supermarkets.fetcher._fetch_product",
                return_value=partial,
            ),
            self.assertRaises(ProviderEvidenceError) as context,
        ):
            fetcher.fetch_product("https://www.dia.es/p/1")

        self.assertEqual(context.exception.missing, GUARDRAIL_NUTRIENT_KEYS[3:])

    def test_fetch_product_returns_product_with_complete_evidence(self) -> None:
        complete = _product(
            nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4],
            ingredients=["leche"],
        )

        with patch(
            "peat_product_scorer.supermarkets.fetcher._fetch_product",
            return_value=complete,
        ):
            self.assertIs(fetcher.fetch_product("https://www.dia.es/p/1"), complete)

    def test_every_provider_path_validates_before_returning(self) -> None:
        partial = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:3], ingredients=["leche"])
        cases = (
            (
                "Mercadona",
                "https://tienda.mercadona.es/product/123/leche",
                "_fetch_mercadona_product",
            ),
            ("DIA", "https://www.dia.es/leche/p/608P6", "_fetch_dia_product"),
            (
                "Alcampo",
                "https://www.compraonline.alcampo.es/products/1",
                "_fetch_alcampo_product",
            ),
            ("Consum", "https://tienda.consum.es/es/p/leche/123", "_fetch_consum_product"),
            (
                "Eroski",
                "https://supermercado.eroski.es/productdetail/123",
                "_fetch_eroski_product",
            ),
        )

        for provider, url, fetch_name in cases:
            with (
                self.subTest(provider=provider),
                patch(
                    f"peat_product_scorer.supermarkets.fetcher.{fetch_name}",
                    return_value=partial,
                ) as fetch_mock,
                self.assertRaises(ProviderEvidenceError),
            ):
                fetcher.fetch_product(url)

            fetch_mock.assert_called_once()

    def test_generic_provider_path_validates_before_returning(self) -> None:
        partial = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:3], ingredients=["leche"])
        response = SimpleNamespace(text="<html></html>", raise_for_status=lambda: None)

        with (
            patch(
                "peat_product_scorer.supermarkets.fetcher._get_supported_product_url",
                return_value=response,
            ),
            patch(
                "peat_product_scorer.supermarkets.fetcher.parse_product_page",
                return_value=partial,
            ),
            self.assertRaises(ProviderEvidenceError),
        ):
            fetcher.fetch_product("https://www.eroski.es/supermercado/p/1")


class CliEvidenceTests(unittest.TestCase):
    def test_score_url_reports_evidence_failure_without_a_traceback(self) -> None:
        with patch(
            "peat_product_scorer.cli.fetch_product",
            side_effect=ProviderEvidenceError("DIA evidence incomplete: missing salt_g."),
        ):
            result = CliRunner().invoke(cli_app, ["score-url", "https://www.dia.es/p/1"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("evidence incomplete", result.output)


class SearchAndScoreEvidenceTests(unittest.TestCase):
    def test_search_tile_metadata_never_produces_a_score(self) -> None:
        tile = SearchResult(
            source="DIA",
            query="queso",
            display_name="Queso en DIA",
            product_id="search-dia-queso",
            url="https://www.dia.es/search?q=queso",
            category="Queso",
        )

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=[tile]),
            patch("peat_product_scorer.scorer.fetch_product") as fetch_mock,
        ):
            results = search_and_score("queso", providers=["DIA"])

        fetch_mock.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].score)
        self.assertIn("no product evidence", results[0].error)

    def test_search_and_score_rejects_unvalidated_partial_product(self) -> None:
        result_row = SearchResult(
            source="DIA",
            query="leche",
            display_name="Leche incompleta",
            product_id="partial",
            url="https://www.dia.es/p/partial",
        )
        partial = _product(nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:3], ingredients=["leche"])

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=[result_row]),
            patch("peat_product_scorer.scorer.fetch_product", return_value=partial),
        ):
            results = search_and_score("leche")

        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].score)
        self.assertIn("saturated_fat_g", results[0].error)

    def test_guardrail_failure_yields_no_score_and_sorts_last(self) -> None:
        incomplete = SearchResult(
            source="DIA",
            query="leche",
            display_name="Leche incompleta",
            product_id="incomplete",
            url="https://www.dia.es/p/incomplete",
        )
        complete = SearchResult(
            source="DIA",
            query="leche",
            display_name="Leche completa",
            product_id="complete",
            url="https://www.dia.es/p/complete",
        )
        complete_product = _product(
            nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4],
            ingredients=["leche entera"],
        )

        def fetch(url: str, timeout: int = 10) -> Product:
            if url.endswith("incomplete"):
                raise ProviderEvidenceError("missing salt_g")
            return complete_product

        with (
            patch(
                "peat_product_scorer.scorer.search_products",
                return_value=[incomplete, complete],
            ),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            results = search_and_score("leche")

        self.assertEqual(
            [result.search.product_id for result in results],
            ["complete", "incomplete"],
        )
        self.assertIsNotNone(results[0].score)
        self.assertIsNone(results[1].score)
        self.assertEqual(results[1].error, "missing salt_g")

    def test_unscored_rows_sort_last_by_name(self) -> None:
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
        complete_product = _product(
            nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4],
            ingredients=["leche entera"],
        )

        def fetch(url: str, timeout: int = 10) -> Product:
            if url.endswith("incomplete"):
                raise ProviderEvidenceError("missing salt_g")
            return complete_product

        with (
            patch(
                "peat_product_scorer.scorer.search_products",
                return_value=[incomplete, complete],
            ),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            results = search_and_score("leche", sort_by="name")

        self.assertEqual(
            [result.search.product_id for result in results],
            ["complete", "incomplete"],
        )

    def test_min_score_filter_excludes_unscored_rows(self) -> None:
        incomplete = SearchResult(
            source="DIA",
            query="leche",
            display_name="Leche incompleta",
            product_id="incomplete",
            url="https://www.dia.es/p/incomplete",
        )
        complete = SearchResult(
            source="DIA",
            query="leche",
            display_name="Leche completa",
            product_id="complete",
            url="https://www.dia.es/p/complete",
        )
        complete_product = _product(
            nutrient_keys=GUARDRAIL_NUTRIENT_KEYS[:4],
            ingredients=["leche entera"],
        )

        def fetch(url: str, timeout: int = 10) -> Product:
            if url.endswith("incomplete"):
                raise ProviderEvidenceError("missing salt_g")
            return complete_product

        with (
            patch(
                "peat_product_scorer.scorer.search_products",
                return_value=[incomplete, complete],
            ),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            results = search_and_score("leche", min_score=0)

        self.assertEqual([result.search.product_id for result in results], ["complete"])
        self.assertIsNotNone(results[0].score)


if __name__ == "__main__":
    unittest.main()

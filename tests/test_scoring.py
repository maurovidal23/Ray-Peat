import unittest
from threading import Barrier
from unittest.mock import patch

from peat_product_scorer.models import Product, SearchResult
from peat_product_scorer.scorer import score_product, search_and_score


class ScoringTests(unittest.TestCase):
    def test_dairy_sugar_product_scores_well(self):
        product = Product(
            name="Yogur natural azucarado",
            ingredients=["leche", "azucar", "fermentos lacticos"],
            nutrition_per_100g={"sugars_g": 12, "protein_g": 4, "calcium_mg": 125, "phosphorus_mg": 95},
        )

        result = score_product(product)

        self.assertGreaterEqual(result.score, 70)
        self.assertIn("fit", result.band)

    def test_seed_oil_product_is_penalized(self):
        product = Product(
            name="Galletas con aceite vegetal",
            ingredients=["harina de trigo", "aceite de girasol", "lecitina de soja"],
            nutrition_per_100g={"fat_g": 24, "sugars_g": 18},
        )

        result = score_product(product)

        self.assertLess(result.score, 45)
        self.assertTrue(any(reason.rule_id == "seed_oils_negative" for reason in result.reasons))

    def test_score_includes_category_components_and_confidence(self):
        product = Product(
            name="Leche entera",
            ingredients=["leche entera de vaca"],
            nutrition_per_100g={"sugars_g": 4.7, "protein_g": 3.1, "calcium_mg": 120, "phosphorus_mg": 92},
        )

        result = score_product(product)

        self.assertEqual(result.category.id, "dairy_milk")
        self.assertGreaterEqual(result.confidence, 60)
        self.assertEqual(
            {component.id for component in result.components},
            {
                "nutrition_profile",
                "ingredient_profile",
                "processing_profile",
                "mineral_fat_quality_profile",
                "evidence_quality",
            },
        )
        self.assertTrue(all(0 <= component.score <= 100 for component in result.components))


class ScoredSearchFallbackTests(unittest.TestCase):
    def test_search_and_score_falls_back_when_fetch_fails(self):
        search_result = SearchResult(
            source="Carrefour Espana",
            query="leche",
            display_name="Leche entera prueba",
            product_id="p1",
            url="https://www.carrefour.es/supermercado/p/leche-entera/p1",
        )

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=[search_result]),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=RuntimeError("blocked")),
        ):
            results = search_and_score("leche", providers=["Carrefour Espana"])

        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0].score)
        self.assertEqual(results[0].error, "blocked")
        self.assertIn("ingredients", results[0].score.product.missing_fields)
        self.assertEqual(results[0].score.product.raw["score_basis"], "search_result_fallback")

    def test_search_and_score_scores_provider_search_fallback_without_fetch(self):
        search_result = SearchResult(
            source="DIA",
            query="queso",
            display_name="Queso en DIA",
            product_id="search-dia-queso",
            url="https://www.dia.es/search?q=queso",
            category="Queso",
        )

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=[search_result]),
            patch("peat_product_scorer.scorer.fetch_product") as fetch_mock,
        ):
            results = search_and_score("queso", providers=["DIA"])

        fetch_mock.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0].score)
        self.assertIn("provider search fallback", results[0].error)
        self.assertEqual(results[0].score.product.raw["score_basis"], "search_result_fallback")

    def test_failed_fetch_ranks_after_successful_fetch_even_with_higher_score(self):
        failed = SearchResult(
            source="DIA",
            query="leche",
            display_name="Leche entera",
            product_id="failed",
            url="https://www.dia.es/p/failed",
        )
        successful = SearchResult(
            source="DIA",
            query="leche",
            display_name="Aceite de girasol",
            product_id="successful",
            url="https://www.dia.es/p/successful",
        )

        def fetch(result_url: str, timeout: int = 10) -> Product:
            if result_url.endswith("failed"):
                raise RuntimeError("blocked")
            return Product(
                name="Aceite de girasol",
                ingredients=["aceite de girasol"],
                nutrition_per_100g={"fat_g": 100},
            )

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=[failed, successful]),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            results = search_and_score("leche")

        self.assertEqual([result.search.product_id for result in results], ["successful", "failed"])
        self.assertIsNone(results[0].error)
        self.assertEqual(results[1].error, "blocked")

    def test_product_fetches_run_concurrently(self):
        search_results = [
            SearchResult(
                source="DIA",
                query="leche",
                display_name=f"Leche {index}",
                product_id=str(index),
                url=f"https://www.dia.es/p/{index}",
            )
            for index in range(2)
        ]
        started = Barrier(2, timeout=2)

        def fetch(result_url: str, timeout: int = 10) -> Product:
            started.wait()
            return Product(name=result_url, ingredients=["leche"], nutrition_per_100g={})

        with (
            patch("peat_product_scorer.scorer.search_products", return_value=search_results),
            patch("peat_product_scorer.scorer.fetch_product", side_effect=fetch),
        ):
            results = search_and_score("leche")

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.error is None for result in results))

if __name__ == "__main__":
    unittest.main()

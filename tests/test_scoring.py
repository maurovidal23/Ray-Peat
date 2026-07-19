import unittest

from peat_product_scorer.models import Product
from peat_product_scorer.scorer import score_product


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


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

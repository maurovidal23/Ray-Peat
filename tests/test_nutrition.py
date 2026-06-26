import unittest

from peat_product_scorer.nutrition import normalize_nutrition, split_ingredients


class NutritionTests(unittest.TestCase):
    def test_normalizes_spanish_labels(self):
        result = normalize_nutrition(
            {
                "Valor energetico": "101 kcal",
                "Grasas": "3,5 g",
                "de las cuales azucares": "12,1 g",
                "Proteinas": "4 g",
            }
        )

        self.assertEqual(result["energy_kcal"], 101)
        self.assertEqual(result["fat_g"], 3.5)
        self.assertEqual(result["sugars_g"], 12.1)
        self.assertEqual(result["protein_g"], 4)

    def test_splits_ingredients(self):
        self.assertEqual(split_ingredients("leche, azucar; fermentos"), ["leche", "azucar", "fermentos"])


if __name__ == "__main__":
    unittest.main()

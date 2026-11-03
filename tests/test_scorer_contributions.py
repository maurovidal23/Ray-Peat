import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from peat_product_scorer.models import Product, ProductScore, ScoreComponent, ScoreContribution
from peat_product_scorer.nutrition import normalize_nutrition, split_ingredients
from peat_product_scorer.scorer import score_product

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _load_example(filename: str) -> Product:
    payload = json.loads((EXAMPLES_DIR / filename).read_text(encoding="utf-8"))
    return Product(
        name=payload["name"],
        source=payload.get("source"),
        brand=payload.get("brand"),
        description=payload.get("description"),
        ingredients=split_ingredients(payload.get("ingredients")),
        nutrition_per_100g=normalize_nutrition(
            payload.get("nutrition_per_100g") or payload.get("nutrition") or {}
        ),
        raw=payload,
    )


def _products() -> dict[str, Product]:
    return {
        "sample_product": _load_example("sample_product.json"),
        "galletas_aceite_girasol": _load_example("galletas_aceite_girasol.json"),
        "yogur_natural_azucarado": Product(
            name="Yogur natural azucarado",
            ingredients=["leche", "azucar", "fermentos lacticos"],
            nutrition_per_100g={
                "sugars_g": 12,
                "protein_g": 4,
                "calcium_mg": 125,
                "phosphorus_mg": 95,
            },
        ),
        "leche_entera": Product(
            name="Leche entera",
            ingredients=["leche entera de vaca"],
            nutrition_per_100g={
                "sugars_g": 4.7,
                "protein_g": 3.1,
                "calcium_mg": 120,
                "phosphorus_mg": 92,
            },
        ),
        "seed_oil_cookies": Product(
            name="Galletas con aceite vegetal",
            ingredients=["harina de trigo", "aceite de girasol", "lecitina de soja"],
            nutrition_per_100g={"fat_g": 24, "sugars_g": 18},
        ),
        "sunflower_oil": Product(
            name="Aceite de girasol",
            ingredients=["aceite de girasol"],
            nutrition_per_100g={
                "fat_g": 100,
                "saturated_fat_g": 15,
                "sugars_g": 0,
                "salt_g": 0,
            },
        ),
    }


def _component(result: ProductScore, component_id: str) -> ScoreComponent:
    return next(component for component in result.components if component.id == component_id)


def _cap_adjustment(result: ProductScore) -> ScoreContribution | None:
    return next(
        (adjustment for adjustment in result.score_adjustments if adjustment.rule_id == "seed_oils_negative"),
        None,
    )


class GoldenCompatibilityTests(unittest.TestCase):
    def test_golden_scores_reasons_and_components_are_unchanged(self):
        golden = json.loads((FIXTURES_DIR / "scorer_golden.json").read_text(encoding="utf-8"))
        products = _products()

        self.assertEqual(set(products), set(golden))
        for name, product in products.items():
            with self.subTest(product=name):
                result = score_product(product)
                expected = golden[name]

                self.assertEqual(result.score, expected["score"])
                self.assertEqual(result.band, expected["band"])
                self.assertEqual(
                    [reason.model_dump(mode="json") for reason in result.reasons],
                    expected["reasons"],
                )
                self.assertEqual(result.warnings, expected["warnings"])

                legacy_components = []
                for component in result.components:
                    dumped = component.model_dump(mode="json")
                    legacy_components.append(
                        {
                            key: dumped[key]
                            for key in ("id", "label", "score", "weight", "reasons", "confidence")
                        }
                    )
                self.assertEqual(legacy_components, expected["components"])


class ContributionReconciliationTests(unittest.TestCase):
    def test_components_reconcile_from_base_plus_contributions(self):
        extra_products = {
            "missing_evidence": Product(name="Sin datos"),
            "stacked_thresholds": Product(
                name="Galleta con azucar",
                ingredients=["harina de trigo"],
                nutrition_per_100g={"sugars_g": 30, "salt_g": 2, "protein_g": 9},
            ),
            "clamped_ingredients": Product(
                name="Producto lacteo",
                ingredients=["leche", "azucar", "gelatina"],
            ),
        }
        products = {**_products(), **extra_products}

        for name, product in products.items():
            with self.subTest(product=name):
                result = score_product(product)
                for component in result.components:
                    contribution_total = sum(
                        contribution.delta for contribution in component.contributions
                    )
                    self.assertEqual(
                        _clamp(component.base_score + contribution_total),
                        component.score,
                    )
                    for contribution in component.contributions:
                        self.assertIn(contribution.kind, {"adjustment", "cap"})
                        self.assertTrue(contribution.detail)

                self.assertAlmostEqual(
                    sum(component.weight for component in result.components),
                    1.0,
                )
                pre_cap_score = _clamp(
                    sum(
                        component.score * component.weight
                        for component in result.components
                    )
                )
                adjustment_total = sum(
                    adjustment.delta for adjustment in result.score_adjustments
                )
                self.assertEqual(pre_cap_score + adjustment_total, result.score)
                for adjustment in result.score_adjustments:
                    self.assertEqual(adjustment.kind, "cap")
                    self.assertEqual(adjustment.rule_id, "seed_oils_negative")


class FrameworkCapTests(unittest.TestCase):
    def test_oil_category_seed_oil_uses_twenty_point_limit(self):
        result = score_product(_products()["sunflower_oil"])
        cap = _cap_adjustment(result)

        self.assertEqual(result.category.id, "oil_or_fat")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.kind, "cap")
        self.assertEqual(result.score, 20)
        self.assertEqual(cap.delta, -40)
        self.assertIn("20", cap.detail)
        self.assertIn("score 60 became 20", cap.detail)

    def test_other_categories_seed_oil_uses_forty_two_point_limit(self):
        result = score_product(_products()["galletas_aceite_girasol"])
        cap = _cap_adjustment(result)

        self.assertNotEqual(result.category.id, "oil_or_fat")
        self.assertIsNotNone(cap)
        self.assertEqual(result.score, 42)
        self.assertEqual(cap.delta, -12)
        self.assertIn("42", cap.detail)
        self.assertIn("score 54 became 42", cap.detail)

    def test_triggered_nonbinding_cap_is_kept_with_zero_delta(self):
        product = Product(
            name="Barrita con aceite de girasol",
            ingredients=[
                "harina de trigo",
                "aceite de girasol",
                "jarabe de glucosa",
                "almidon modificado",
                "aspartamo",
                "aroma",
                "emulgente",
                "proteina aislada",
                "goma guar",
                "fosfato",
                "hierro",
                "sal",
                "lecitina de soja",
            ],
            nutrition_per_100g={"fat_g": 30, "sugars_g": 40, "salt_g": 2},
            missing_fields=["ingredients", "nutrition_per_100g"],
        )

        result = score_product(product)
        cap = _cap_adjustment(result)

        self.assertEqual(result.category.id, "oil_or_fat")
        self.assertIsNotNone(cap)
        self.assertEqual(result.score, 20)
        self.assertEqual(cap.delta, 0)
        self.assertIn("20", cap.detail)
        self.assertIn("score 20 became 20", cap.detail)

    def test_no_cap_record_without_seed_oil_trigger(self):
        for name in ("sample_product", "leche_entera"):
            with self.subTest(product=name):
                result = score_product(_products()[name])
                self.assertEqual(result.score_adjustments, [])
                self.assertFalse(
                    any(reason.rule_id == "seed_oils_negative" for reason in result.reasons)
                )


class MissingEvidenceAndBoundaryTests(unittest.TestCase):
    def test_missing_ingredients_and_nutrition_use_fallback_bases(self):
        result = score_product(Product(name="Sin datos"))
        bases = {component.id: component.base_score for component in result.components}

        self.assertEqual(
            bases,
            {
                "nutrition_profile": 50,
                "ingredient_profile": 62,
                "processing_profile": 45,
                "mineral_fat_quality_profile": 58,
                "evidence_quality": 100,
            },
        )
        self.assertEqual(_component(result, "nutrition_profile").contributions, [])
        self.assertEqual(_component(result, "processing_profile").contributions, [])

        evidence = _component(result, "evidence_quality")
        self.assertEqual(evidence.score, 40)
        self.assertEqual(
            [(contribution.rule_id, contribution.delta) for contribution in evidence.contributions],
            [("missing_ingredients", -35), ("missing_nutrition", -25)],
        )

    def test_missing_field_flags_are_independent_evidence_deductions(self):
        result = score_product(
            Product(
                name="Sin datos declarados",
                missing_fields=["ingredients", "nutrition_per_100g"],
            )
        )
        evidence = _component(result, "evidence_quality")

        self.assertEqual(evidence.score, 15)
        self.assertEqual(
            [(contribution.rule_id, contribution.delta) for contribution in evidence.contributions],
            [
                ("missing_ingredients", -35),
                ("missing_nutrition", -25),
                ("ingredients_missing_field", -15),
                ("nutrition_missing_field", -10),
            ],
        )

    def test_processing_base_depends_on_ingredient_count(self):
        neutral_ingredients = [
            "agua",
            "sal",
            "harina",
            "azucar",
            "leche",
            "huevo",
            "tomate",
            "arroz",
            "pollo",
            "pescado",
            "aceituna",
        ]

        for count, expected_base, expected_score in [
            (1, 92, 92),
            (2, 92, 92),
            (3, 78, 78),
            (6, 78, 78),
            (7, 60, 60),
            (10, 60, 60),
            (11, 60, 50),
        ]:
            with self.subTest(ingredient_count=count):
                product = Product(
                    name="Producto neutro",
                    ingredients=neutral_ingredients[:count],
                )
                processing = _component(score_product(product), "processing_profile")
                self.assertEqual(processing.base_score, expected_base)
                self.assertEqual(processing.score, expected_score)
                if count > 10:
                    self.assertEqual(
                        [(contribution.rule_id, contribution.delta) for contribution in processing.contributions],
                        [("long_ingredient_list", -10)],
                    )

    def test_component_scores_are_clamped_at_their_bounds(self):
        result = score_product(
            Product(
                name="Producto lacteo",
                ingredients=["leche", "azucar", "gelatina"],
            )
        )
        ingredients = _component(result, "ingredient_profile")

        self.assertEqual(ingredients.base_score, 62)
        self.assertEqual(
            ingredients.base_score + sum(
                contribution.delta for contribution in ingredients.contributions
            ),
            102,
        )
        self.assertEqual(ingredients.score, 100)


class NumericStepTests(unittest.TestCase):
    def test_stacked_sugar_and_salt_thresholds_emit_independent_steps(self):
        result = score_product(
            Product(
                name="Galleta con azucar",
                ingredients=["harina de trigo"],
                nutrition_per_100g={"sugars_g": 30, "salt_g": 2, "protein_g": 9},
            )
        )
        nutrition = _component(result, "nutrition_profile")

        self.assertEqual(
            [(contribution.rule_id, contribution.delta) for contribution in nutrition.contributions],
            [
                ("sugar_high_negative", -8),
                ("sugar_very_high_negative", -8),
                ("protein_high_positive", 8),
                ("salt_high_negative", -10),
            ],
        )
        self.assertEqual(nutrition.score, 42)

    def test_dairy_sugar_thresholds_emit_both_sides_when_stacked(self):
        result = score_product(
            Product(
                name="Yogur muy azucarado",
                ingredients=["leche", "azucar"],
                nutrition_per_100g={"sugars_g": 30},
            )
        )
        nutrition = _component(result, "nutrition_profile")
        sugar_contributions = [
            (contribution.rule_id, contribution.delta)
            for contribution in nutrition.contributions
            if "sugar" in (contribution.rule_id or "")
        ]

        self.assertEqual(
            sugar_contributions,
            [("sugar_dairy_positive", 6), ("sugar_dairy_high_negative", -8)],
        )

    def test_moderate_salt_and_saturated_fat_steps_are_emitted(self):
        result = score_product(
            Product(
                name="Galleta salada",
                ingredients=["harina de trigo"],
                nutrition_per_100g={"salt_g": 1, "saturated_fat_g": 6},
            )
        )
        nutrition = _component(result, "nutrition_profile")

        self.assertEqual(
            [(contribution.rule_id, contribution.delta) for contribution in nutrition.contributions],
            [("saturated_fat_high_negative", -8), ("salt_moderate_negative", -4)],
        )
        self.assertEqual(nutrition.score, 48)

    def test_ingredient_multiplier_rounding_is_recorded(self):
        result = score_product(_products()["galletas_aceite_girasol"])
        ingredients = _component(result, "ingredient_profile")
        fruit = next(
            contribution
            for contribution in ingredients.contributions
            if contribution.rule_id == "fruit_sugar_positive"
        )

        self.assertEqual(fruit.delta, 6)
        self.assertIn("0.65", fruit.detail)
        self.assertIn("6.5", fruit.detail)
        self.assertIn("rounded to +6", fruit.detail)
        self.assertEqual(ingredients.score, 54)

    def test_ingredient_multiplier_is_not_applied_without_a_major_negative(self):
        result = score_product(
            Product(
                name="Zumo de naranja",
                ingredients=["zumo", "naranja"],
            )
        )
        ingredients = _component(result, "ingredient_profile")
        fruit = next(
            contribution
            for contribution in ingredients.contributions
            if contribution.rule_id == "fruit_sugar_positive"
        )

        self.assertEqual(fruit.delta, 10)
        self.assertIn("applied directly", fruit.detail)
        self.assertEqual(ingredients.score, 78)

    def test_mineral_and_fat_rules_and_ratio_bonus_reconcile(self):
        result = score_product(_products()["sample_product"])
        mineral_fat = _component(result, "mineral_fat_quality_profile")
        contributions = {
            contribution.rule_id: contribution for contribution in mineral_fat.contributions
        }

        self.assertEqual(contributions["calcium_phosphorus_positive"].delta, 12)
        ratio = contributions["calcium_phosphorus_ratio_positive"]
        self.assertEqual(ratio.delta, 10)
        self.assertIn("125", ratio.detail)
        self.assertIn("95", ratio.detail)
        self.assertIn("1.32", ratio.detail)
        self.assertEqual(mineral_fat.score, 80)

    def test_missing_ratio_bonus_is_not_emitted(self):
        result = score_product(
            Product(
                name="Queso con fosforo alto",
                ingredients=["queso"],
                nutrition_per_100g={"calcium_mg": 50, "phosphorus_mg": 100},
            )
        )
        mineral_fat = _component(result, "mineral_fat_quality_profile")

        self.assertFalse(
            any(
                contribution.rule_id == "calcium_phosphorus_ratio_positive"
                for contribution in mineral_fat.contributions
            )
        )

    def test_oil_category_seed_penalty_is_a_separate_step(self):
        result = score_product(_products()["sunflower_oil"])
        mineral_fat = _component(result, "mineral_fat_quality_profile")
        oil_penalty = next(
            contribution
            for contribution in mineral_fat.contributions
            if contribution.rule_id == "seed_oil_oil_category_penalty"
        )

        self.assertEqual(oil_penalty.delta, -18)
        self.assertIn("girasol", oil_penalty.detail)
        self.assertIn("-18", oil_penalty.detail)
        self.assertEqual(mineral_fat.score, 9)


class AdditiveSerializationTests(unittest.TestCase):
    def test_score_payload_only_adds_contribution_fields(self):
        result = score_product(_products()["sample_product"])
        payload = result.model_dump(mode="json")

        self.assertTrue(
            {
                "score",
                "band",
                "comment",
                "reasons",
                "product",
                "confidence",
                "category",
                "components",
                "warnings",
                "score_adjustments",
            }.issubset(payload)
        )
        self.assertIsInstance(payload["score_adjustments"], list)
        for component in payload["components"]:
            self.assertIn("base_score", component)
            self.assertIn("contributions", component)
            for contribution in component["contributions"]:
                self.assertEqual(
                    set(contribution),
                    {"label", "delta", "detail", "kind", "rule_id"},
                )

    def test_contribution_kind_accepts_only_adjustment_or_cap(self):
        adjustment = ScoreContribution(label="Step", delta=1, detail="A step")
        cap = ScoreContribution(label="Cap", delta=0, detail="A cap", kind="cap")

        self.assertEqual(adjustment.kind, "adjustment")
        self.assertEqual(cap.kind, "cap")
        with self.assertRaises(ValidationError):
            ScoreContribution(label="Invalid", delta=1, detail="Invalid kind", kind="other")

    def test_default_lists_are_independent(self):
        first = ScoreComponent(id="a", label="A", score=1, base_score=1, weight=0.1)
        second = ScoreComponent(id="b", label="B", score=1, base_score=1, weight=0.1)
        first.contributions.append(ScoreContribution(label="Step", delta=1, detail="A step"))
        self.assertEqual(second.contributions, [])

        first_score = ProductScore(
            score=1,
            band="avoid",
            comment="",
            reasons=[],
            product=Product(name="First"),
        )
        second_score = ProductScore(
            score=1,
            band="avoid",
            comment="",
            reasons=[],
            product=Product(name="Second"),
        )
        first_score.score_adjustments.append(
            ScoreContribution(label="Cap", delta=-1, detail="A cap", kind="cap")
        )
        self.assertEqual(second_score.score_adjustments, [])


if __name__ == "__main__":
    unittest.main()

import unittest

from peat_product_scorer.supermarkets.adapters import supermarket_name_for_url
from peat_product_scorer.supermarkets.fetcher import (
    _bonpreu_entity_from_state,
    _build_product,
    _consum_ingredient_text,
    _load_bonpreu_initial_state,
    _product_from_bonpreu_entity,
    _standardize_ingredient_text,
    _strip_html,
)


class SupermarketStandardizationTests(unittest.TestCase):
    def test_product_title_is_not_used_as_ingredient_evidence(self) -> None:
        product = _build_product(
            name="Aceite de Girasol Alto Oleico",
            source="Consum",
            url="https://example.test/product",
            description="Aceite de Girasol Alto Oleico",
            ingredient_text="Aceite de Girasol Alto Oleico",
            nutrition_raw={},
        )

        self.assertEqual(product.ingredients, [])
        self.assertIsNone(product.ingredient_text)
        self.assertIn("ingredients", product.missing_fields)
        self.assertIn("nutrition_per_100g", product.missing_fields)

    def test_consum_ingredient_text_requires_ingredient_labeled_attribute(self) -> None:
        product_data = {
            "attributeGroups": [
                {
                    "name": "Informaci?n del producto",
                    "attributes": [
                        {
                            "code": "filter.id.brand.distributor",
                            "name": None,
                            "languages": [{"values": ["1"]}],
                        },
                        {
                            "code": "product.ingredients",
                            "name": "Ingredientes",
                            "languages": [{"values": ["Leche entera de vaca"]}],
                        },
                    ],
                }
            ]
        }

        self.assertEqual(_consum_ingredient_text(product_data), "Leche entera de vaca")

    def test_ingredient_prefix_and_duplicate_parts_are_standardized(self) -> None:
        product = _build_product(
            name="Test",
            source="Manual",
            url="https://example.test/product",
            ingredient_text="Ingredientes: leche entera; leche entera, sal.",
            nutrition_raw={"Sal": "0,1 g"},
        )

        self.assertEqual(product.ingredient_text, "leche entera; leche entera, sal")
        self.assertEqual(product.ingredients, ["leche entera", "sal"])
        self.assertEqual(product.nutrition_per_100g["salt_g"], 0.1)
        self.assertEqual(product.missing_fields, [])


    def test_researched_supermarket_domains_are_recognized(self) -> None:
        self.assertEqual(
            supermarket_name_for_url("https://www.compraonline.bonpreuesclat.cat/search?q=llet"),
            "Bon Preu / Esclat",
        )
        self.assertEqual(supermarket_name_for_url("https://www.aldi.es/ofertas.html"), "Aldi ES")
        self.assertEqual(supermarket_name_for_url("https://www.hipercor.es/supermercado/"), "Hipercor")

    def test_bonpreu_initial_state_product_is_standardized(self) -> None:
        html = '<script>window.__INITIAL_STATE__ = {"data":{"products":{"productEntities":{"p1":{"productId":"p1","retailerProductId":"23597","name":"BONPREU Llet sencera 6x1L en cartro","brand":"BONPREU","categoryPath":["Lactics i ous","Llets"],"size":{"value":"6x1L"},"price":{"current":{"amount":"5.40","currency":"EUR"}}}}},"search":{"catalogue":{"data":{"productGroups":[{"type":"cluster","products":["p1"]}]}}}}};</script>'
        state = _load_bonpreu_initial_state(html)
        entity = _bonpreu_entity_from_state(state, "https://www.compraonline.bonpreuesclat.cat/search?q=llet")
        product = _product_from_bonpreu_entity(
            entity,
            url="https://www.compraonline.bonpreuesclat.cat/search?q=llet",
        )

        self.assertEqual(product.name, "BONPREU Llet sencera 6x1L en cartro")
        self.assertEqual(product.source, "Bon Preu / Esclat")
        self.assertEqual(product.brand, "BONPREU")
        self.assertIn("ingredients", product.missing_fields)
        self.assertIn("nutrition_per_100g", product.missing_fields)

    def test_html_entities_are_removed_from_ingredient_text(self) -> None:
        self.assertEqual(_strip_html("leche&nbsp;en polvo &amp; cacao"), "leche en polvo & cacao")

    def test_standardize_ingredient_text_returns_none_for_empty_or_weak_value(self) -> None:
        self.assertIsNone(_standardize_ingredient_text(None, name="A", description=None))
        self.assertIsNone(_standardize_ingredient_text("A", name="A", description=None))


if __name__ == "__main__":
    unittest.main()

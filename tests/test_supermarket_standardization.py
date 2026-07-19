import unittest
from unittest.mock import patch

from peat_product_scorer.models import SearchResult
from peat_product_scorer.supermarkets.adapters import supermarket_name_for_url
from peat_product_scorer.supermarkets.fetcher import (
    _bonpreu_entity_from_state,
    _build_product,
    _consum_ingredient_text,
    _dia_product_id,
    _interleave_search_results,
    _load_bonpreu_initial_state,
    _product_from_bonpreu_entity,
    _search_generic_provider,
    search_products,
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

    def test_dia_product_id_accepts_pack_skus(self) -> None:
        self.assertEqual(
            _dia_product_id("https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"),
            "608P6",
        )

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

    def test_generic_provider_search_extracts_product_links(self) -> None:
        class FakeResponse:
            text = """
            <html><body>
              <a href="/products/auchan-leche-entera/54178">
                <img src="/img/leche.jpg" alt="Auchan leche entera">
              </a>
              <a href="/search?text=leche">Search page</a>
            </body></html>
            """

            def raise_for_status(self) -> None:
                return None

        with patch("peat_product_scorer.supermarkets.fetcher.requests.get", return_value=FakeResponse()):
            results = _search_generic_provider(
                "Alcampo",
                "https://www.compraonline.alcampo.es/search?text={query}",
                "compraonline.alcampo.es",
                "leche",
                5,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "Alcampo")
        self.assertEqual(results[0].display_name, "Auchan leche entera")
        self.assertEqual(results[0].thumbnail, "https://www.compraonline.alcampo.es/img/leche.jpg")

    def test_search_results_are_interleaved_across_providers(self) -> None:
        dia = SearchResult(source="DIA", query="leche", display_name="DIA leche", product_id="1", url="https://www.dia.es/p/1")
        alcampo = SearchResult(source="Alcampo", query="leche", display_name="Alcampo leche", product_id="2", url="https://www.compraonline.alcampo.es/products/2")
        consum = SearchResult(source="Consum", query="leche", display_name="Consum leche", product_id="3", url="https://tienda.consum.es/es/p/leche/3")

        results = _interleave_search_results([[dia], [alcampo], [consum]], max_results=3)

        self.assertEqual([result.source for result in results], ["DIA", "Alcampo", "Consum"])

    def test_search_products_filters_selected_provider(self) -> None:
        selected = SearchResult(
            source="Alcampo",
            query="leche",
            display_name="Alcampo leche",
            product_id="2",
            url="https://www.compraonline.alcampo.es/products/2",
        )

        with (
            patch("peat_product_scorer.supermarkets.fetcher._search_dia", return_value=[]) as dia_mock,
            patch("peat_product_scorer.supermarkets.fetcher._search_mercadona_categories", return_value=[]) as mercadona_mock,
            patch("peat_product_scorer.supermarkets.fetcher._search_generic_provider", return_value=[selected]) as generic_mock,
        ):
            results = search_products("leche", max_results=5, providers=["Alcampo"])

        dia_mock.assert_not_called()
        mercadona_mock.assert_not_called()
        generic_mock.assert_called_once()
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual({result.source for result in results}, {"Alcampo"})

    def test_search_products_uses_provider_fallback_catalog(self) -> None:
        with (
            patch("peat_product_scorer.supermarkets.fetcher._search_dia", return_value=[]),
            patch("peat_product_scorer.supermarkets.fetcher._search_mercadona_categories", return_value=[]),
            patch("peat_product_scorer.supermarkets.fetcher._search_generic_provider", return_value=[]),
        ):
            dia_results = search_products("leche", max_results=3, providers=["DIA"])
            alcampo_results = search_products("leche", max_results=3, providers=["Alcampo"])

        self.assertEqual([result.source for result in dia_results], ["DIA"])
        self.assertEqual([result.source for result in alcampo_results], ["Alcampo"])
        self.assertIn("608P6", dia_results[0].url)
        self.assertIn("54178", alcampo_results[0].url)

    def test_search_products_normalizes_generic_browser_terms(self) -> None:
        with (
            patch("peat_product_scorer.supermarkets.fetcher._search_dia", return_value=[]),
            patch("peat_product_scorer.supermarkets.fetcher._search_mercadona_categories", return_value=[]),
            patch("peat_product_scorer.supermarkets.fetcher._search_generic_provider", return_value=[]),
        ):
            dia_results = search_products("product", max_results=3, providers=["DIA"])
            alcampo_results = search_products("None", max_results=3, providers=["Alcampo"])

        self.assertEqual([result.source for result in dia_results], ["DIA"])
        self.assertEqual(dia_results[0].query, "leche")
        self.assertEqual([result.source for result in alcampo_results], ["Alcampo"])
        self.assertEqual(alcampo_results[0].query, "leche")

if __name__ == "__main__":
    unittest.main()

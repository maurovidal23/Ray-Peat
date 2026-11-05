import unittest
from types import SimpleNamespace
from unittest.mock import patch

from peat_product_scorer.models import SearchResult
from peat_product_scorer.supermarkets.adapters import supermarket_name_for_url
from peat_product_scorer.supermarkets.fetcher import (
    RELIABLE_SEARCH_PROVIDERS,
    _build_product,
    _interleave_search_results,
    _search_generic_provider,
    _standardize_ingredient_text,
    _strip_html,
    fetch_product,
    search_products,
)


class SupermarketStandardizationTests(unittest.TestCase):
    def test_supermarket_matching_rejects_deceptive_domain_suffixes(self) -> None:
        self.assertEqual(
            supermarket_name_for_url("https://supermercado.eroski.es/productdetail/1"),
            "Eroski",
        )
        self.assertEqual(
            supermarket_name_for_url("https://eroski.es.attacker.example/productdetail/1"),
            "Unknown supermarket",
        )

    def test_product_title_is_not_used_as_ingredient_evidence(self) -> None:
        product = _build_product(
            name="Aceite de Girasol Alto Oleico",
            source="Eroski",
            url="https://example.test/product",
            description="Aceite de Girasol Alto Oleico",
            ingredient_text="Aceite de Girasol Alto Oleico",
            nutrition_raw={},
        )

        self.assertEqual(product.ingredients, [])
        self.assertIsNone(product.ingredient_text)
        self.assertIn("ingredients", product.missing_fields)
        self.assertIn("nutrition_per_100g", product.missing_fields)

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

    def test_conforming_supermarket_domains_are_recognized(self) -> None:
        self.assertEqual(
            supermarket_name_for_url("https://supermercado.eroski.es/productdetail/1"),
            "Eroski",
        )

    def test_unsupported_domains_are_not_recognized(self) -> None:
        self.assertEqual(
            supermarket_name_for_url("https://www.example.com/supermercado/producto/1"),
            "Unknown supermarket",
        )

    def test_html_entities_are_removed_from_ingredient_text(self) -> None:
        self.assertEqual(_strip_html("leche&nbsp;en polvo &amp; cacao"), "leche en polvo & cacao")

    def test_standardize_ingredient_text_returns_none_for_empty_or_weak_value(self) -> None:
        self.assertIsNone(_standardize_ingredient_text(None, name="A", description=None))
        self.assertIsNone(_standardize_ingredient_text("A", name="A", description=None))

    def test_generic_provider_search_extracts_product_links(self) -> None:
        class FakeResponse:
            text = """
            <html><body>
              <a href="/es/productdetail/18672295-leche-entera">
                <img src="/img/leche.jpg" alt="Leche entera Eroski">
              </a>
              <a href="/es/search/results/?q=leche">Search page</a>
            </body></html>
            """

            def raise_for_status(self) -> None:
                return None

        with patch("peat_product_scorer.supermarkets.fetcher.requests.get", return_value=FakeResponse()):
            results = _search_generic_provider(
                "Eroski",
                "https://supermercado.eroski.es/es/search/results/?q={query}",
                "supermercado.eroski.es",
                "leche",
                5,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "Eroski")
        self.assertEqual(results[0].display_name, "Leche entera Eroski")
        self.assertEqual(results[0].thumbnail, "https://supermercado.eroski.es/img/leche.jpg")

    def test_search_results_are_interleaved_across_providers(self) -> None:
        first = SearchResult(source="Eroski", query="leche", display_name="Eroski leche", product_id="1", url="https://example.test/1")
        second = SearchResult(source="Manual", query="leche", display_name="Manual leche", product_id="2", url="https://example.test/2")
        third = SearchResult(source="Test", query="leche", display_name="Test leche", product_id="3", url="https://example.test/3")

        results = _interleave_search_results([[first], [second], [third]], max_results=3)

        self.assertEqual([result.source for result in results], ["Eroski", "Manual", "Test"])

    def test_search_products_filters_selected_provider(self) -> None:
        selected = SearchResult(
            source="Eroski",
            query="leche",
            display_name="Eroski leche",
            product_id="2",
            url="https://supermercado.eroski.es/productdetail/2",
        )

        with patch(
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
            return_value=[selected],
        ) as generic_mock:
            results = search_products("leche", max_results=5, providers=["Eroski"])

        generic_mock.assert_called_once()
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual({result.source for result in results}, {"Eroski"})

    def test_default_search_queries_only_reliable_providers(self) -> None:
        self.assertEqual(RELIABLE_SEARCH_PROVIDERS, ("Eroski",))

        with patch(
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
            return_value=[],
        ) as generic:
            search_products("leche", max_results=5, providers=["all"])

        queried_sources = {call.args[0] for call in generic.call_args_list}
        self.assertEqual(queried_sources, {"Eroski"})

    def test_selected_provider_honors_requested_limit_above_eight(self) -> None:
        products = [
            SearchResult(
                source="Eroski",
                query="leche",
                display_name=f"Leche {index}",
                product_id=str(index),
                url=f"https://supermercado.eroski.es/productdetail/{index}",
            )
            for index in range(12)
        ]
        with patch(
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
            return_value=products,
        ) as generic:
            results = search_products("leche", max_results=12, providers=["Eroski"])

        self.assertEqual(len(results), 12)
        self.assertEqual(generic.call_args.args[-1], 12)

    def test_product_redirect_cannot_escape_supported_hosts(self) -> None:
        with (
            patch(
                "peat_product_scorer.supermarkets.fetcher.requests.get",
                return_value=SimpleNamespace(
                    status_code=302,
                    headers={"location": "http://169.254.169.254/latest/meta-data/"},
                ),
            ) as get_mock,
            self.assertRaisesRegex(ValueError, "IP address"),
        ):
            fetch_product("https://supermercado.eroski.es/productdetail/example")

        get_mock.assert_called_once()

    def test_fetch_product_rejects_unsafe_urls_before_any_network_request(self) -> None:
        urls = (
            "https://user:password@supermercado.eroski.es/productdetail/1",
            "https://supermercado.eroski.es:8443/productdetail/1",
            "https://169.254.169.254/latest/meta-data/",
            "https://supermercado.eroski.es.attacker.example/productdetail/1",
            "https://www.example.com/supermercado/producto/1",
        )

        with patch("peat_product_scorer.supermarkets.fetcher.requests.get") as get_mock:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    fetch_product(url)

        get_mock.assert_not_called()

    def test_search_products_does_not_invent_provider_results(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
            return_value=[],
        ):
            eroski_results = search_products("miel", max_results=3, providers=["Eroski"])

        self.assertEqual(eroski_results, [])

    def test_search_products_normalizes_generic_browser_terms(self) -> None:
        with patch(
            "peat_product_scorer.supermarkets.fetcher._search_generic_provider",
            return_value=[],
        ):
            product_results = search_products("product", max_results=3, providers=["Eroski"])
            none_results = search_products("None", max_results=3, providers=["Eroski"])

        self.assertEqual(product_results, [])
        self.assertEqual(none_results, [])


if __name__ == "__main__":
    unittest.main()

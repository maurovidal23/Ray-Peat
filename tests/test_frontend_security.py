import re
import unittest
from pathlib import Path


APP_JS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "peat_product_scorer"
    / "static"
    / "app.js"
)


class FrontendSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = APP_JS.read_text(encoding="utf-8")

    def test_api_values_are_never_rendered_as_html(self) -> None:
        """Provider text such as '<img onerror=...>' must remain plain text."""
        self.assertNotIn(".innerHTML", self.source)
        self.assertIn("element.textContent =", self.source)
        self.assertIn("renderEmptyState(els.bestProductsList", self.source)

    def test_best_product_links_require_http_or_https(self) -> None:
        render_best_products = re.search(
            r"function renderBestProducts\(results\) \{(?P<body>.*?)\n\}",
            self.source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(render_best_products)
        body = render_best_products.group("body")
        self.assertIn("if (isHttpUrl(sourceUrl))", body)
        self.assertIn('sourceLink.rel = "noopener noreferrer"', body)

        url_validator = re.search(
            r"function isHttpUrl\(value\) \{(?P<body>.*?)\n\}",
            self.source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(url_validator)
        validator_body = url_validator.group("body")
        self.assertIn('url.protocol === "http:"', validator_body)
        self.assertIn('url.protocol === "https:"', validator_body)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


STATIC_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "peat_product_scorer" / "static"
)
APP_JS = STATIC_DIR / "app.js"
INDEX_HTML = STATIC_DIR / "index.html"
STYLES_CSS = STATIC_DIR / "styles.css"


class FrontendExplainabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = APP_JS.read_text(encoding="utf-8")
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        cls.css = STYLES_CSS.read_text(encoding="utf-8")

    def test_how_scoring_links_point_to_methodology_page(self) -> None:
        self.assertGreaterEqual(self.html.count("ⓘ How scoring works"), 3)
        self.assertIn('class="how-scoring-link" href="/"', self.html)
        self.assertGreaterEqual(self.html.count('class="how-scoring-link" href="/"'), 2)

        evaluator_heading = self.html.index("Algorithm components")
        heading_markup = self.html[evaluator_heading:evaluator_heading + 500]
        self.assertIn("ⓘ How scoring works", heading_markup)

    def test_explanation_registry_covers_components_and_meta_values(self) -> None:
        for label in (
            "Nutrition profile",
            "Ingredient profile",
            "Processing profile",
            "Mineral and fat quality",
            "Evidence quality",
            "Weight",
            "Band",
            "Confidence",
        ):
            self.assertIn(f'label: "{label}"', self.js)

    def test_popover_uses_text_content_and_accessibility_attributes(self) -> None:
        self.assertIn("document.createElement", self.js)
        self.assertIn("element.textContent =", self.js)
        self.assertIn('setAttribute("role", "tooltip")', self.js)
        self.assertIn('setAttribute("aria-describedby", popover.id)', self.js)
        self.assertIn('setAttribute("aria-hidden", "false")', self.js)
        self.assertIn('if (event.key === "Escape") closeExplanation();', self.js)
        self.assertIn('document.addEventListener("focusout"', self.js)
        self.assertIn('document.addEventListener("mouseout"', self.js)
        self.assertIn("data-explain", self.js)

    def test_no_prohibited_html_sinks(self) -> None:
        for sink in (".innerHTML", "insertAdjacentHTML", "outerHTML", "document.write"):
            self.assertNotIn(sink, self.js)
            self.assertNotIn(sink, self.html)

    def test_component_breakdown_only_appears_for_non_empty_contributions(self) -> None:
        self.assertIn("if (!Array.isArray(raw) || raw.length === 0) return [];", self.js)
        self.assertIn("buildContributionBreakdown", self.js)
        self.assertIn("Base score:", self.js)
        self.assertIn("Weighted effect:", self.js)
        self.assertIn("score * weight", self.js)
        self.assertIn('setAttribute("aria-expanded", "false")', self.js)
        self.assertIn('setAttribute("aria-controls", panelId)', self.js)

    def test_guardrail_failure_has_exact_phrase_and_provider_error(self) -> None:
        self.assertGreaterEqual(self.js.count("Insufficient evidence to score"), 2)
        self.assertIn("renderInsufficientEvidence(result, product)", self.js)
        self.assertIn("if (!hasScoreValue(result.score))", self.js)
        self.assertIn("provider_error", self.js)
        self.assertIn("unscored-note", self.js)
        self.assertIn("unscored-detail", self.js)

    def test_styles_cover_popover_breakdown_and_empty_state(self) -> None:
        for selector in (
            ".explanation-popover",
            ".how-scoring-link",
            ".component-breakdown",
            ".breakdown-toggle",
            ".band.unscored",
        ):
            self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()

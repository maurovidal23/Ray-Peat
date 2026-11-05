import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests
from typer.testing import CliRunner

from peat_product_scorer.cli import app as cli_app
from peat_product_scorer.supermarkets.adapters import ADAPTERS

AUDIT_PATH = Path(__file__).resolve().parents[1] / "docs" / "provider_audit.md"

ISSUE_PROVIDERS = (
    "DIA",
    "Mercadona",
    "Alcampo",
    "Eroski",
    "Consum",
    "Carrefour España",
    "El Corte Inglés",
    "Lidl Spain",
    "Aldi ES",
    "Spar ES",
    "Hipercor",
    "Gadis Online",
    "Covirán",
    "Caprabo",
    "Condis",
    "Froiz",
    "Bon Preu / Esclat",
    "Open Food Facts",
)


class ProviderAuditDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = AUDIT_PATH.read_text(encoding="utf-8")

    def test_audit_document_exists(self) -> None:
        self.assertTrue(AUDIT_PATH.is_file())

    def test_status_table_lists_every_issue_provider(self) -> None:
        status_table = self.document.split("## Structured live matrix", 1)[0]

        for provider in ISSUE_PROVIDERS:
            with self.subTest(provider=provider):
                self.assertIn(f"| **{provider}** |", status_table)

    def test_every_registered_adapter_appears_in_the_audit_table(self) -> None:
        status_table = self.document.split("## Structured live matrix", 1)[0]

        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter.name):
                self.assertIn(f"| **{adapter.name}** |", status_table)

    def test_every_registered_adapter_is_classified_keep_or_remove(self) -> None:
        classification_section = self.document.split("## Keep / remove decision", 1)[1]
        classification_section = classification_section.split("**Keep:**", 1)[0]
        classifications = dict(
            re.findall(
                r"^\| \*\*(?P<provider>[^*]+)\*\* \| (?P<decision>[^|]+) \|$",
                classification_section,
                flags=re.MULTILINE,
            )
        )

        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter.name):
                decision = classifications.get(adapter.name)
                self.assertIsNotNone(
                    decision,
                    f"{adapter.name} is registered but missing from the audit keep/remove list",
                )
                self.assertTrue(decision.startswith(("keep", "remove")))

    def test_keep_list_is_a_subset_of_registered_providers(self) -> None:
        classification_section = self.document.split("## Keep / remove decision", 1)[1]
        classification_section = classification_section.split("**Keep:**", 1)[0]
        classifications = dict(
            re.findall(
                r"^\| \*\*(?P<provider>[^*]+)\*\* \| (?P<decision>[^|]+) \|$",
                classification_section,
                flags=re.MULTILINE,
            )
        )

        keep = {provider for provider, decision in classifications.items() if decision.startswith("keep")}
        registered = {adapter.name for adapter in ADAPTERS}
        self.assertTrue(
            keep <= registered,
            f"audit keep list contains providers missing from adapters.py: {keep - registered}",
        )


class RemovedProviderCliTests(unittest.TestCase):
    def test_search_score_rejects_a_removed_provider(self) -> None:
        result = CliRunner().invoke(
            cli_app,
            ["search-score", "leche", "--source", "Carrefour"],
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("not a verified provider", result.output)
        self.assertIn("evidence guardrail", result.output)
        self.assertNotIn("No products found", result.output)

    def test_score_url_rejects_a_removed_provider_domain(self) -> None:
        result = CliRunner().invoke(
            cli_app,
            ["score-url", "https://www.carrefour.es/supermercado/el-producto/123"],
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("not a supported supermarket", result.output)

    def test_score_url_reports_a_blocked_fetch_without_a_traceback(self) -> None:
        blocked = requests.HTTPError(
            "HTTP 403",
            response=SimpleNamespace(status_code=403),
        )
        with patch("peat_product_scorer.cli.fetch_product", side_effect=blocked):
            result = CliRunner().invoke(
                cli_app,
                ["score-url", "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"],
            )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Provider fetch failed (blocked): HTTP 403", result.output)
        self.assertNotIn("Traceback", result.output)


if __name__ == "__main__":
    unittest.main()

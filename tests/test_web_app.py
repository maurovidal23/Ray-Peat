import unittest

from fastapi.testclient import TestClient

from peat_product_scorer.web_app import app


class WebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_score_endpoint_accepts_product_payload(self) -> None:
        response = self.client.post(
            "/api/score",
            json={
                "product": {
                    "name": "Aceite de girasol test",
                    "source": "Manual",
                    "ingredients": "Aceite refinado de girasol",
                    "nutrition": {"grasas": "100 g"},
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["band"], "avoid")
        self.assertEqual(data["product"]["nutrition_per_100g"]["fat_g"], 100.0)

    def test_articles_endpoint_lists_formatted_article_library(self) -> None:
        response = self.client.get("/api/articles")

        self.assertEqual(response.status_code, 200)
        articles = response.json()["articles"]
        self.assertGreater(len(articles), 50)
        self.assertIn("excerpt", articles[0])
        self.assertNotIn("url", articles[0])

    def test_article_detail_endpoint_returns_paragraphs(self) -> None:
        articles = self.client.get("/api/articles").json()["articles"]
        response = self.client.get(f"/api/articles/{articles[0]['id']}")

        self.assertEqual(response.status_code, 200)
        article = response.json()
        self.assertGreater(len(article["paragraphs"]), 1)
        self.assertEqual(article["id"], articles[0]["id"])

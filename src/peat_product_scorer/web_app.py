from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .models import Product
from .nutrition import normalize_nutrition, split_ingredients
from .scorer import score_product
from .supermarkets import fetch_product
from .supermarkets.adapters import ADAPTERS

STATIC_DIR = Path(__file__).resolve().parent / "static"
ARTICLE_DATA_PATH = STATIC_DIR / "articles" / "ray_peat_articles.json"


class ScoreRequest(BaseModel):
    url: str | None = Field(default=None, description="Spanish supermarket product URL")
    product: dict[str, Any] | None = Field(default=None, description="Raw product payload")


app = FastAPI(
    title="Ray Peat Product Scorer",
    version=__version__,
    description="Scores Spanish supermarket products with an explainable Ray Peat-inspired rule set.",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/articles", include_in_schema=False)
def articles_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/articles/{article_id}", include_in_schema=False)
def article_page(article_id: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "service": "ray-peat-product-scorer",
        "connectors": [adapter.name for adapter in ADAPTERS],
    }


@app.get("/api/connectors")
def connectors() -> dict[str, Any]:
    verified = {"Mercadona", "DIA", "Alcampo", "Consum", "Eroski"}
    return {
        "connectors": [
            {
                "name": adapter.name,
                "domains": list(adapter.domains),
                "status": "verified" if adapter.name in verified else "fallback",
            }
            for adapter in ADAPTERS
        ]
    }


@app.get("/api/articles")
def articles() -> dict[str, Any]:
    return {
        "articles": [
            {
                "id": article["id"],
                "title": article["title"],
                "languages": article["languages"],
                "default_language": article["default_language"],
                "excerpt": article["excerpt"],
                "word_count": article["word_count"],
            }
            for article in _load_articles()
        ]
    }


@app.get("/api/articles/{article_id}")
def article_detail(article_id: str, lang: str | None = None) -> dict[str, Any]:
    for article in _load_articles():
        if article["id"] != article_id:
            continue
        variant = _select_article_variant(article, lang)
        return {
            "id": article["id"],
            "languages": article["languages"],
            "selected_language": variant["language"],
            "title": variant["title"],
            "source_pdf": variant["source_pdf"],
            "paragraphs": variant["paragraphs"],
            "excerpt": variant["excerpt"],
            "word_count": variant["word_count"],
        }
    raise HTTPException(status_code=404, detail="Article not found.")


def _select_article_variant(article: dict[str, Any], lang: str | None) -> dict[str, Any]:
    variants = article.get("variants", [])
    if not variants:
        raise HTTPException(status_code=404, detail="Article variant not found.")
    if lang:
        for variant in variants:
            if variant["language"] == lang:
                return variant
        raise HTTPException(status_code=404, detail=f"Article is not available in language '{lang}'.")
    for variant in variants:
        if variant["language"] == article.get("default_language"):
            return variant
    return variants[0]


@app.post("/api/score")
def score(request: ScoreRequest) -> dict[str, Any]:
    if request.url:
        product = _fetch_product_for_api(request.url)
    elif request.product:
        product = _product_from_payload(request.product)
    else:
        raise HTTPException(status_code=422, detail="Provide either url or product.")

    result = score_product(product)
    return result.model_dump(mode="json")


def _fetch_product_for_api(url: str) -> Product:
    try:
        return fetch_product(url)
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        raise HTTPException(
            status_code=502,
            detail=f"Supermarket request failed with HTTP {status_code}.",
        ) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Supermarket request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _product_from_payload(payload: dict[str, Any]) -> Product:
    nutrition = payload.get("nutrition_per_100g") or payload.get("nutrition") or {}
    try:
        return Product(
            name=payload["name"],
            source=payload.get("source"),
            url=payload.get("url"),
            brand=payload.get("brand"),
            description=payload.get("description"),
            ingredients=split_ingredients(payload.get("ingredients")),
            nutrition_per_100g=normalize_nutrition(nutrition),
            raw=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail="Product payload requires a name.") from exc


@lru_cache(maxsize=1)
def _load_articles() -> list[dict[str, Any]]:
    try:
        data = json.loads(ARTICLE_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("Article data file is missing.") from exc
    return data.get("articles", [])

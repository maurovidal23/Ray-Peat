from __future__ import annotations

from pathlib import Path
from typing import Any
from unicodedata import normalize
from urllib.parse import quote

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
ARTICLE_PDF_DIR = STATIC_DIR / "articles" / "pdfs"


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
    files = sorted(ARTICLE_PDF_DIR.glob("*.pdf"), key=lambda path: _article_title(path).lower())
    return {
        "articles": [
            {
                "title": _article_title(path),
                "filename": path.name,
                "language": _article_language(path),
                "kind": "book" if path.name == "Ray_Peat_Libro.pdf" else "article",
                "url": f"/static/articles/pdfs/{quote(path.name)}",
            }
            for path in files
        ]
    }


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


def _article_title(path: Path) -> str:
    if path.name == "Ray_Peat_Libro.pdf":
        return "Ray Peat Libro"
    return path.stem.replace("_", " ").strip()


def _article_language(path: Path) -> str:
    title = normalize("NFKD", _article_title(path)).encode("ascii", "ignore").decode().casefold()
    if title.startswith("el ") or title.startswith("sin titulo"):
        return "es"
    if title.startswith("ruolo "):
        return "other"
    return "en"

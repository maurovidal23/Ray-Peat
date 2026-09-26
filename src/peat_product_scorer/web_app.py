from __future__ import annotations

import ipaddress
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from . import __version__
from .models import Product
from .nutrition import normalize_nutrition, split_ingredients
from .scorer import score_product, search_and_score
from .supermarkets import fetch_product, search_products
from .supermarkets.adapters import ADAPTERS
from .supermarkets.fetcher import available_search_providers

STATIC_DIR = Path(__file__).resolve().parent / "static"
ARTICLE_DATA_PATH = STATIC_DIR / "articles" / "ray_peat_articles.json"
EN_LIBRARY_PAGE = STATIC_DIR / "library" / "en" / "index.html"
ES_LIBRARY_PAGE = STATIC_DIR / "library" / "es" / "index.html"


MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_INGREDIENT_TEXT_LENGTH = 10_000


class ProductPayload(BaseModel):
    """Bounded user-supplied product data accepted by the scoring API."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    source: str | None = Field(default=None, max_length=100)
    url: HttpUrl | None = None
    brand: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4_000)
    ingredients: str | list[Annotated[str, Field(min_length=1, max_length=500)]] | None = None
    nutrition: dict[str, str | int | float] | None = None
    nutrition_per_100g: dict[str, str | int | float] | None = None

    @field_validator("ingredients", mode="before")
    @classmethod
    def validate_ingredients(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, str):
            if len(value) > MAX_INGREDIENT_TEXT_LENGTH:
                raise ValueError("ingredients text is too long")
            return value
        if not isinstance(value, list):
            # Pydantic v2 intentionally lets TypeError escape instead of producing a 422.
            raise ValueError("ingredients must be text or a list of text values")  # noqa: TRY004
        if len(value) > 100:
            raise ValueError("ingredients may contain at most 100 items")
        if sum(len(item) for item in value if isinstance(item, str)) > MAX_INGREDIENT_TEXT_LENGTH:
            raise ValueError("combined ingredients text is too long")
        return value

    @field_validator("nutrition", "nutrition_per_100g", mode="before")
    @classmethod
    def validate_nutrition(cls, value: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("nutrition must be an object")  # noqa: TRY004
        if len(value) > 64:
            raise ValueError("nutrition may contain at most 64 values")
        for label, amount in value.items():
            if not isinstance(label, str) or not label or len(label) > 100:
                raise ValueError("nutrition labels must be non-empty text up to 100 characters")
            if isinstance(amount, bool) or not isinstance(amount, (str, int, float)):
                raise ValueError("nutrition amounts must be text or numbers")  # noqa: TRY004
            if isinstance(amount, str) and len(amount) > 100:
                raise ValueError("nutrition amounts may be at most 100 characters")
            if isinstance(amount, float) and not math.isfinite(amount):
                raise ValueError("nutrition amounts must be finite")
        return value


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(
        default=None,
        max_length=2_048,
        description="Spanish supermarket product URL",
    )
    product: ProductPayload | None = Field(default=None, description="Product payload")

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return _normalize_product_url(value) if value is not None else None

    @model_validator(mode="after")
    def require_one_input(self) -> ScoreRequest:
        if (self.url is None) == (self.product is None):
            raise ValueError("Provide exactly one of url or product.")
        return self


app = FastAPI(
    title="Ray Peat Product Scorer",
    version=__version__,
    description="Scores Spanish supermarket products with an explainable Ray Peat-inspired rule set.",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def limit_request_body(request: Request, call_next: Any) -> Any:
    """Reject oversized API writes before JSON parsing and model validation."""
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body is too large."},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )
        body = await request.body()
        if len(body) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
    return await call_next(request)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(EN_LIBRARY_PAGE)


@app.get("/evaluator", include_in_schema=False)
def evaluator_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/products", include_in_schema=False)
def products_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/articles", include_in_schema=False)
def articles_page() -> FileResponse:
    return FileResponse(EN_LIBRARY_PAGE)


@app.get("/articles/{article_id}", include_in_schema=False)
def article_page(article_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/articles#article/{article_id}")


@app.get("/articles-es", include_in_schema=False)
def articles_page_es() -> FileResponse:
    return FileResponse(ES_LIBRARY_PAGE)


@app.get("/articles-es/{article_id}", include_in_schema=False)
def article_page_es(article_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/articles-es#article/{article_id}")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "service": "ray-peat-product-scorer",
        "connectors": [adapter.name for adapter in ADAPTERS],
    }


@app.get("/api/version")
def api_version() -> dict[str, str]:
    return {"version": __version__, "build": "dia-search-back"}


@app.get("/api/connectors")
def connectors() -> dict[str, Any]:
    verified = {"Mercadona", "DIA", "Alcampo", "Consum", "Eroski"}
    partial = {"Bon Preu / Esclat"}
    return {
        "connectors": [
            {
                "name": adapter.name,
                "domains": list(adapter.domains),
                "status": _connector_status(adapter.name, verified=verified, partial=partial),
            }
            for adapter in ADAPTERS
        ]
    }


class SearchQuery(BaseModel):
    q: str = Field(..., min_length=1, description="Search query")
    max_results: int = Field(default=10, ge=1, le=20, description="Maximum results")
    provider: str | None = Field(default=None, description="Provider name or 'all'")

    @property
    def providers(self) -> list[str] | None:
        if not self.provider or self.provider.lower() == "all":
            return None
        return [self.provider]


@app.get("/api/search-providers")
def search_provider_options() -> dict[str, Any]:
    return {"providers": ["all", *available_search_providers()]}


@app.post("/api/search")
def search_endpoint(query: SearchQuery) -> dict[str, Any]:
    results = search_products(query.q, max_results=query.max_results, providers=query.providers)
    return {
        "query": query.q,
        "provider": query.provider or "all",
        "total": len(results),
        "results": [r.model_dump(mode="json") for r in results],
    }


@app.post("/api/search-score")
def search_and_score_endpoint(query: SearchQuery) -> dict[str, Any]:
    scored = search_and_score(
        query.q,
        max_results=query.max_results,
        max_per_source=query.max_results,
        providers=query.providers,
    )
    return {
        "query": query.q,
        "provider": query.provider or "all",
        "total": len(scored),
        "results": [s.model_dump(mode="json", exclude_none=True) for s in scored],
    }


def _connector_status(name: str, *, verified: set[str], partial: set[str]) -> str:
    if name in verified:
        return "verified"
    if name in partial:
        return "partial"
    return "fallback"


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
    elif request.product is not None:
        product = _product_from_payload(request.product)
    else:
        raise HTTPException(status_code=422, detail="Provide exactly one of url or product.")

    result = score_product(product)
    return result.model_dump(mode="json")


def _normalize_product_url(value: str) -> str:
    url = value.strip()
    if not url:
        raise ValueError("Product URL must not be empty.")
    if not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Product URL must use HTTP or HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Product URL must not contain credentials.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Product URL has an invalid port.") from exc
    if port is not None and port != {"http": 80, "https": 443}[parsed.scheme.lower()]:
        raise ValueError("Product URL must not use a nonstandard port.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Product URL must include a hostname.")
    hostname = hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Product URL must not use an IP address.")

    supported_domains = {
        domain.lower().rstrip(".") for adapter in ADAPTERS for domain in adapter.domains
    }
    if not any(hostname == domain or hostname.endswith(f".{domain}") for domain in supported_domains):
        raise ValueError("Product URL hostname is not a supported supermarket.")

    netloc = hostname
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, parsed.query, parsed.fragment))


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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Product extraction failed: {exc}") from exc


def _product_from_payload(payload: ProductPayload) -> Product:
    nutrition = payload.nutrition_per_100g or payload.nutrition or {}
    ingredient_text = payload.ingredients
    ingredients = split_ingredients(ingredient_text)
    nutrition_per_100g = normalize_nutrition(nutrition)
    missing_fields = []
    if not ingredients:
        missing_fields.append("ingredients")
    if not nutrition_per_100g:
        missing_fields.append("nutrition_per_100g")
    return Product(
        name=payload.name,
        source=payload.source,
        url=payload.url,
        brand=payload.brand,
        description=payload.description,
        ingredient_text=", ".join(ingredients) if isinstance(ingredient_text, list) else ingredient_text,
        ingredient_source="manual_payload" if ingredients else None,
        ingredients=ingredients,
        nutrition_per_100g=nutrition_per_100g,
        missing_fields=missing_fields,
        # Never retain or return the caller's complete request document.
        raw={},
    )


@lru_cache(maxsize=1)
def _load_articles() -> list[dict[str, Any]]:
    try:
        data = json.loads(ARTICLE_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("Article data file is missing.") from exc
    return data.get("articles", [])

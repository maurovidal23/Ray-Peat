from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse

import requests

from ..models import Product, SearchResult
from ..nutrition import split_ingredients
from .contract import ProductProvider, ProviderEvidenceError, validate_provider_url

BASE_URL = "https://world.openfoodfacts.org"
SOURCE = "Open Food Facts"
USER_AGENT = "Ray-Peat-Product-Scorer/0.1 (+https://github.com/maurovidal23/Ray-Peat)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}
SEARCH_PATH = "/api/v2/search"
PRODUCT_PATH = "/api/v2/product/{code}"

# Open Food Facts nutriment field -> the normalized key consumed by the scorer.
NUTRIMENT_KEYS = {
    "sugars_100g": "sugars_g",
    "proteins_100g": "protein_g",
    "fat_100g": "fat_g",
    "saturated-fat_100g": "saturated_fat_g",
    "salt_100g": "salt_g",
    "carbohydrates_100g": "carbohydrate_g",
    "fiber_100g": "fiber_g",
    "calcium_100g": "calcium_mg",
    "phosphorus_100g": "phosphorus_mg",
}

SEARCH_FIELDS = (
    "code",
    "product_name",
    "product_name_es",
    "generic_name",
    "generic_name_es",
    "brands",
    "categories_tags",
    "image_front_small_url",
    "ingredients_text_es",
    "nutriments",
)


class OpenFoodFactsProvider(ProductProvider):
    """Provider backed by the Open Food Facts API v2."""

    @property
    def name(self) -> str:
        return SOURCE

    @property
    def domains(self) -> tuple[str, ...]:
        return ("openfoodfacts.org", "world.openfoodfacts.org")

    def search(
        self,
        query: str,
        max_results: int = 10,
        timeout: int = 15,
    ) -> list[SearchResult]:
        if max_results <= 0 or not query.strip():
            return []
        try:
            response = requests.get(
                f"{BASE_URL}{SEARCH_PATH}",
                params={
                    "search_terms": query,
                    "countries_tags_en": "spain",
                    "page_size": max_results,
                    "fields": ",".join(SEARCH_FIELDS),
                },
                headers=HEADERS,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return []
        if not isinstance(payload, dict):
            return []

        results: list[SearchResult] = []
        seen_codes: set[str] = set()
        for item in payload.get("products") or []:
            if len(results) >= max_results:
                break
            if not isinstance(item, dict):
                continue
            code = _normalize_code(item.get("code"))
            if not code or code in seen_codes:
                continue
            product = _product_from_payload(item, code=code)
            try:
                _require_conforming_evidence(product)
            except ProviderEvidenceError:
                continue
            seen_codes.add(code)
            results.append(
                SearchResult(
                    source=SOURCE,
                    query=query,
                    display_name=_product_name(item) or code,
                    product_id=code,
                    url=product_url(code),
                    brand=_text(item.get("brands")),
                    price=None,
                    price_currency=None,
                    thumbnail=_text(item.get("image_front_small_url")),
                    category=_category(item),
                )
            )
        return results

    def fetch(self, url: str, timeout: int = 20) -> Product:
        validate_provider_url(url, self.domains)
        code = _code_from_url(url)
        return self.fetch_by_code(code, timeout=timeout)

    def fetch_by_code(self, code: str, timeout: int = 20) -> Product:
        code = _normalize_code(code)
        if not code:
            raise ValueError("Open Food Facts product code is required.")
        try:
            response = requests.get(
                f"{BASE_URL}{PRODUCT_PATH.format(code=code)}",
                headers=HEADERS,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError:
            raise
        except requests.RequestException as exc:
            raise ProviderEvidenceError(
                f"Open Food Facts request failed: {exc}",
            ) from exc
        except ValueError as exc:
            raise ProviderEvidenceError(
                "Open Food Facts returned an invalid JSON response.",
            ) from exc

        if not isinstance(payload, dict):
            raise ProviderEvidenceError("Open Food Facts returned an invalid response.")
        status = payload.get("status")
        if status not in (1, "1"):
            raise ProviderEvidenceError(
                f"Open Food Facts product {code} is not available.",
            )
        product_payload = payload.get("product")
        if not isinstance(product_payload, dict) or not product_payload:
            raise ProviderEvidenceError(
                f"Open Food Facts product {code} is not available.",
            )
        return _product_from_payload(product_payload, code=code)


OPENFOODFACTS_PROVIDER = OpenFoodFactsProvider()


def search(query: str, max_results: int = 10, timeout: int = 15) -> list[SearchResult]:
    return OPENFOODFACTS_PROVIDER.search(query, max_results=max_results, timeout=timeout)


def fetch(url: str, timeout: int = 20) -> Product:
    return OPENFOODFACTS_PROVIDER.fetch(url, timeout=timeout)


def product_url(code: str) -> str:
    return f"{BASE_URL}/product/{_normalize_code(code)}"


def _require_conforming_evidence(product: Product) -> Product:
    # Search results are only useful when they can be scored without inventing data.
    from .contract import require_evidence

    return require_evidence(product, source=SOURCE)


def _product_from_payload(payload: dict[str, Any], *, code: str) -> Product:
    ingredient_text = _clean_ingredient_text(_text(payload.get("ingredients_text_es")))
    ingredients = split_ingredients(ingredient_text)
    nutrition = _nutrition(payload.get("nutriments"))

    missing_fields: list[str] = []
    if not ingredients:
        missing_fields.append("ingredients")
    if not nutrition:
        missing_fields.append("nutrition_per_100g")

    return Product(
        name=_product_name(payload) or code,
        source=SOURCE,
        url=product_url(code),
        brand=_text(payload.get("brands")),
        description=_text(payload.get("generic_name_es")) or _text(payload.get("generic_name")),
        ingredient_text=ingredient_text,
        ingredient_source="openfoodfacts.ingredients_text_es" if ingredients else None,
        ingredients=ingredients,
        nutrition_per_100g=nutrition,
        missing_fields=missing_fields,
        raw={
            "openfoodfacts_product": payload,
            "extraction": {
                "ingredient_source": (
                    "openfoodfacts.ingredients_text_es" if ingredients else None
                ),
                "has_ingredients": bool(ingredients),
                "has_nutrition_per_100g": bool(nutrition),
                "missing_fields": missing_fields,
            },
        },
    )


def _nutrition(nutriments: Any) -> dict[str, float]:
    if not isinstance(nutriments, dict):
        return {}
    nutrition: dict[str, float] = {}
    for field, key in NUTRIMENT_KEYS.items():
        value = _number(nutriments.get(field))
        if value is not None:
            nutrition[key] = value
    # Some exports use an underscore instead of the documented hyphen.
    if "saturated_fat_g" not in nutrition:
        value = _number(nutriments.get("saturated_fat_100g"))
        if value is not None:
            nutrition["saturated_fat_g"] = value
    # The evidence guardrail looks for total carbohydrate under carbs_g.
    if "carbohydrate_g" in nutrition:
        nutrition["carbs_g"] = nutrition["carbohydrate_g"]
    return nutrition


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:[,.]\d+)?", value)
        if not match:
            return None
        try:
            number = float(match.group(0).replace(",", "."))
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _product_name(payload: dict[str, Any]) -> str:
    for key in ("product_name_es", "product_name", "generic_name_es", "generic_name"):
        value = _text(payload.get(key))
        if value:
            return value
    return ""


def _category(payload: dict[str, Any]) -> str | None:
    categories = payload.get("categories_tags")
    if isinstance(categories, list):
        for category in categories:
            text = _text(category)
            if text:
                return text
    return None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _clean_ingredient_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"^\s*ingredientes\s*:?\s*", "", value, flags=re.IGNORECASE)
    return cleaned.strip(" .") or None


def _normalize_code(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).strip())


def _code_from_url(url: str) -> str:
    path = urlparse(url).path
    match = re.search(r"/product/([^/?#]+)", path)
    if not match:
        raise ValueError("Open Food Facts product URL must include a product code.")
    return _normalize_code(match.group(1))

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from ..models import Product
from ..nutrition import normalize_nutrition, split_ingredients


def parse_product_page(html: str, url: str, source: str) -> Product:
    soup = BeautifulSoup(html, "html.parser")
    json_ld = _extract_json_ld_product(soup)
    visible_text = soup.get_text("\n", strip=True)

    name = (
        _first_string(json_ld.get("name"))
        or _meta_content(soup, "og:title")
        or _title_text(soup)
        or "Unknown product"
    )
    brand = _first_string(json_ld.get("brand"))
    description = _first_string(json_ld.get("description")) or _meta_content(soup, "description")
    ingredients = split_ingredients(
        json_ld.get("ingredients")
        or json_ld.get("recipeIngredient")
        or _extract_labeled_block(visible_text, ["Ingredientes", "Ingredients"])
    )
    nutrition = normalize_nutrition(_extract_nutrition(json_ld, visible_text))

    return Product(
        name=name,
        source=source,
        url=url,
        brand=brand,
        description=description,
        ingredients=ingredients,
        nutrition_per_100g=nutrition,
        raw={"json_ld": json_ld},
    )


def _extract_json_ld_product(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.select('script[type="application/ld+json"]'):
        if not script.string:
            continue
        try:
            payload = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        product = _find_product_payload(payload)
        if product:
            return product
    return {}


def _find_product_payload(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, list):
        for item in payload:
            found = _find_product_payload(item)
            if found:
                return found
    if isinstance(payload, dict):
        if payload.get("@type") == "Product":
            return payload
        graph = payload.get("@graph")
        if graph:
            return _find_product_payload(graph)
    return None


def _extract_nutrition(json_ld: dict[str, Any], text: str) -> dict[str, object]:
    nutrition = json_ld.get("nutrition")
    if isinstance(nutrition, dict):
        return nutrition

    found: dict[str, object] = {}
    patterns = {
        "energy_kcal": r"(?:energia|valor energetico)[^\d]{0,30}(\d+(?:[,.]\d+)?)\s*kcal",
        "fat_g": r"grasas?[^\d]{0,30}(\d+(?:[,.]\d+)?)\s*g",
        "saturated_fat_g": r"saturadas?[^\d]{0,30}(\d+(?:[,.]\d+)?)\s*g",
        "carbohydrate_g": r"hidratos de carbono[^\d]{0,30}(\d+(?:[,.]\d+)?)\s*g",
        "sugars_g": r"az[uú]cares?[^\d]{0,30}(\d+(?:[,.]\d+)?)\s*g",
        "protein_g": r"prote[ií]nas?[^\d]{0,30}(\d+(?:[,.]\d+)?)\s*g",
        "salt_g": r"sal[^\d]{0,30}(\d+(?:[,.]\d+)?)\s*g",
    }
    lower_text = text.lower()
    for key, pattern in patterns.items():
        match = re.search(pattern, lower_text)
        if match:
            found[key] = match.group(1)
    return found


def _extract_labeled_block(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = rf"{label}\s*:?\s*(.+?)(?:\n[A-ZÁÉÍÓÚÑ][^\n]{{2,40}}\n|$)"
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


def _first_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "@value"):
            result = _first_string(value.get(key))
            if result:
                return result
    return None


def _meta_content(soup: BeautifulSoup, name: str) -> str | None:
    selector = f'meta[property="{name}"], meta[name="{name}"]'
    tag = soup.select_one(selector)
    content = tag.get("content") if tag else None
    return content.strip() if content else None


def _title_text(soup: BeautifulSoup) -> str | None:
    return soup.title.string.strip() if soup.title and soup.title.string else None

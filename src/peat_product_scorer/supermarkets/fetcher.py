from __future__ import annotations

import json
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from ..models import Product
from ..nutrition import normalize_nutrition, split_ingredients
from .adapters import supermarket_name_for_url
from .parser import parse_product_page


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"}


def fetch_product(url: str, timeout: int = 20) -> Product:
    if "tienda.mercadona.es" in url:
        product_id = _mercadona_product_id(url)
        if product_id:
            return _fetch_mercadona_product(product_id, timeout=timeout)

    if "dia.es" in url and "/p/" in url:
        return _fetch_dia_product(url, timeout=timeout)

    if "compraonline.alcampo.es" in url and "/products/" in url:
        return _fetch_alcampo_product(url, timeout=timeout)

    if "tienda.consum.es" in url and "/p/" in url:
        product_code = _consum_product_code(url)
        if product_code:
            return _fetch_consum_product(product_code, timeout=timeout)

    if "supermercado.eroski.es" in url and "/productdetail/" in url:
        return _fetch_eroski_product(url, timeout=timeout)

    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    source = supermarket_name_for_url(url)
    return parse_product_page(response.text, url=url, source=source)

def _mercadona_product_id(url: str) -> str | None:
    match = re.search(r"/(?:product|products)/(\d+)", url)
    return match.group(1) if match else None


def _fetch_mercadona_product(product_id: str, timeout: int) -> Product:
    api_url = f"https://tienda.mercadona.es/api/products/{product_id}"
    response = requests.get(api_url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    details = payload.get("details") or {}
    nutrition_info = payload.get("nutrition_information") or {}
    raw_nutrition = nutrition_info.get("nutrition_values") or nutrition_info.get("values") or {}
    ingredients_html = nutrition_info.get("ingredients") or ""
    ingredients_text = _strip_html(ingredients_html)
    ingredients_text = re.sub(r"^\s*ingredientes\s*:\s*", "", ingredients_text, flags=re.IGNORECASE)

    return Product(
        name=payload.get("display_name") or details.get("description") or "Unknown Mercadona product",
        source="Mercadona",
        url=payload.get("share_url") or api_url,
        brand=payload.get("brand") or details.get("brand"),
        description=details.get("description") or details.get("legal_name"),
        ingredients=split_ingredients(ingredients_text),
        nutrition_per_100g=normalize_nutrition(_flatten_nutrition(raw_nutrition)),
        raw={"mercadona_api": payload},
    )


def _fetch_dia_product(url: str, timeout: int) -> Product:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    context = _load_script_json(soup, "vike_pageContext")
    product = ((context.get("INITIAL_STATE") or {}).get("product") or {}) if context else {}

    if not product:
        return parse_product_page(response.text, url=url, source="DIA")

    title = (product.get("primary_info") or {}).get("title") or product.get("sku_id") or "Unknown DIA product"
    ingredients = _strip_html((product.get("ingredients") or {}).get("text") or "")
    nutritional_info = product.get("nutritional_info") or {}
    raw_nutrition = _dia_nutrition(nutritional_info)

    return Product(
        name=title,
        source="DIA",
        url=url,
        brand=_dia_brand_from_title(title),
        description=(product.get("product_info") or {}).get("product"),
        ingredients=split_ingredients(ingredients),
        nutrition_per_100g=normalize_nutrition(raw_nutrition),
        raw={"dia_page_context_product": product},
    )


def _fetch_alcampo_product(url: str, timeout: int) -> Product:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    generic = parse_product_page(response.text, url=url, source="Alcampo")
    sections = _alcampo_sections(soup)
    nutrition = _table_to_mapping(sections.get("Datos nutricionales"))
    characteristics = _table_to_mapping(sections.get("Características"))
    ingredients = sections.get("Ingredientes") or ""
    brand = sections.get("Marca")

    return Product(
        name=generic.name,
        source="Alcampo",
        url=url,
        brand=brand,
        description=characteristics.get("Denominación legal del alimento") or generic.description,
        ingredients=split_ingredients(_clean_ingredient_prefix(ingredients)),
        nutrition_per_100g=normalize_nutrition(nutrition) or generic.nutrition_per_100g,
        raw={"alcampo_sections": sections, "json_ld": generic.raw.get("json_ld")},
    )



def _consum_product_code(url: str) -> str | None:
    match = re.search(r"/p/[^/]+/(\d+)(?:[/?#]|$)", url)
    return match.group(1) if match else None


def _fetch_consum_product(product_code: str, timeout: int) -> Product:
    api_url = f"https://tienda.consum.es/api/rest/V1.0/catalog/product/code/{product_code}"
    headers = {
        **HEADERS,
        "Accept": "application/json",
        "x-locale": "es",
        "x-currency": "EUR",
        "x-zone": "0",
    }
    response = requests.get(api_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    product_data = payload.get("productData") or {}
    brand = product_data.get("brand") or {}
    name = product_data.get("name") or f"Consum product {product_code}"
    description = product_data.get("description") or product_data.get("seoDescription")
    evidence = _consum_attribute_text(product_data) or " ".join(part for part in [name, description or ""] if part)

    return Product(
        name=name,
        source="Consum",
        url=product_data.get("url") or api_url,
        brand=brand.get("name") if isinstance(brand, dict) else None,
        description=description,
        ingredients=split_ingredients(evidence),
        nutrition_per_100g=normalize_nutrition(_consum_nutrition(product_data)),
        raw={"consum_api": payload},
    )


def _consum_attribute_text(product_data: dict[str, Any]) -> str:
    values: list[str] = []
    for group in product_data.get("attributeGroups") or []:
        for attribute in group.get("attributes") or []:
            code = str(attribute.get("code") or "").lower()
            if code.startswith("hidden.") or code.startswith("filter."):
                continue
            for language in attribute.get("languages") or []:
                for value in language.get("values") or []:
                    if isinstance(value, str) and value.strip():
                        values.append(value.strip())
    return ", ".join(values)


def _consum_nutrition(product_data: dict[str, Any]) -> dict[str, object]:
    nutrition: dict[str, object] = {}
    for group in product_data.get("attributeGroups") or []:
        group_name = str(group.get("name") or "").lower()
        if "nutri" not in group_name and "valor" not in group_name:
            continue
        for attribute in group.get("attributes") or []:
            label = str(attribute.get("name") or attribute.get("code") or "")
            for language in attribute.get("languages") or []:
                values = language.get("values") or []
                if values:
                    nutrition[label] = values[0]
    return nutrition

def _fetch_eroski_product(url: str, timeout: int) -> Product:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    generic = parse_product_page(response.text, url=url, source="Eroski")
    ingredients = _eroski_feature_text(soup, "Ingredientes")
    nutrition = _eroski_nutrition(soup)
    brand = _eroski_brand(generic.name)

    return Product(
        name=generic.name,
        source="Eroski",
        url=url,
        brand=brand,
        description=generic.description,
        ingredients=split_ingredients(ingredients),
        nutrition_per_100g=normalize_nutrition(nutrition) or generic.nutrition_per_100g,
        raw={"json_ld": generic.raw.get("json_ld"), "eroski_nutrition": nutrition},
    )


def _eroski_feature_text(soup: BeautifulSoup, title: str) -> str:
    for title_node in soup.select("span.title"):
        if title_node.get_text(" ", strip=True).lower() != title.lower():
            continue
        container = title_node.find_parent(class_=re.compile(r"feature"))
        if not container:
            continue
        texts = [node.get_text(" ", strip=True) for node in container.select("p.text")]
        return " ".join(text for text in texts if text)
    return ""


def _eroski_nutrition(soup: BeautifulSoup) -> dict[str, object]:
    nutrition: dict[str, object] = {}
    for title_node in soup.select("span.title"):
        if "nutricional" not in title_node.get_text(" ", strip=True).lower():
            continue
        container = title_node.find_parent(class_=re.compile(r"feature"))
        if not container:
            continue
        for item in container.select("li"):
            amount = item.find("span")
            if not amount:
                continue
            label = item.get_text(" ", strip=True).replace(amount.get_text(" ", strip=True), "").strip()
            value = _normalize_eroski_amount(amount.get_text(" ", strip=True))
            if not label or not value:
                continue
            if label.lower() == "energía" and "kj" in value.lower():
                key = "Kilojulios"
            else:
                key = "Valor energetico" if label.lower() == "energía" and "kcal" in value.lower() else label
            nutrition[key] = value
    return nutrition


def _normalize_eroski_amount(value: str) -> str:
    replacements = [
        ("kilocaloría it (international table)", "kcal"),
        ("kilocaloria it (international table)", "kcal"),
        ("kilojulios", "kJ"),
        ("miligramos", "mg"),
        ("gramos", "g"),
    ]
    normalized = value
    for old, new in replacements:
        normalized = re.sub(old, new, normalized, flags=re.IGNORECASE)
    return normalized

def _eroski_brand(name: str) -> str | None:
    known = ["Eroski", "Kaiku", "Pascual", "Central Lechera Asturiana", "Puleva"]
    lowered = name.lower()
    for brand in known:
        if brand.lower() in lowered:
            return brand
    return None
def _load_script_json(soup: BeautifulSoup, script_id: str) -> dict[str, Any]:
    tag = soup.find("script", id=script_id)
    if not tag or not tag.string:
        return {}
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return {}


def _dia_nutrition(nutritional_info: dict[str, Any]) -> dict[str, object]:
    values = nutritional_info.get("nutritional_values") or {}
    raw: dict[str, object] = {}
    if values.get("energy_value") is not None:
        raw["Valor energetico"] = values.get("energy_value")
    for item in values.get("values") or []:
        title = item.get("title")
        if title:
            raw[title] = item.get("value_per_100_g", item.get("value"))
        for child in item.get("items") or []:
            child_title = child.get("title")
            if child_title:
                raw[child_title] = child.get("value_per_100_g", child.get("value"))
    for item in (nutritional_info.get("vitamins") or {}).get("values") or []:
        title = item.get("title")
        if title:
            raw[title] = item.get("value")
    return raw


def _alcampo_sections(soup: BeautifulSoup) -> dict[str, str]:
    sections: dict[str, str] = {}
    for heading in soup.find_all("h2"):
        title = heading.get_text(" ", strip=True)
        container = heading.find_parent("div")
        if not title or not container:
            continue
        content_parts = []
        for sibling in heading.find_next_siblings():
            content_parts.append(sibling.get_text(" ", strip=True))
        text = " ".join(part for part in content_parts if part).strip()
        if text:
            sections[title] = text
    return sections


def _table_to_mapping(text: str | None) -> dict[str, object]:
    if not text:
        return {}
    pairs: dict[str, object] = {}
    cleaned = re.sub(r"\s+", " ", text).strip()
    patterns = [
        r"(Valor energético \(Kcal\))\s+(\d+(?:[,.]\d+)?\s*Kcal)",
        r"(Valor energético \(Kj\))\s+(\d+(?:[,.]\d+)?\s*Kj)",
        r"(Grasas saturadas)\s+(\d+(?:[,.]\d+)?\s*g)",
        r"(Grasas)\s+(\d+(?:[,.]\d+)?\s*g)",
        r"(Hidratos de carbono)\s+(\d+(?:[,.]\d+)?\s*g)",
        r"(Azúcares)\s+(\d+(?:[,.]\d+)?\s*g)",
        r"(Proteinas|Proteínas)\s+(\d+(?:[,.]\d+)?\s*g)",
        r"(Sal)\s+(\d+(?:[,.]\d+)?\s*g)",
        r"(Calcio)\s+(\d+(?:[,.]\d+)?\s*mg)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            pairs[match.group(1)] = match.group(2)
    return pairs


def _strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _clean_ingredient_prefix(value: str) -> str:
    value = re.sub(r"^\s*ingredientes\s*:?\s*", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def _dia_brand_from_title(title: str) -> str | None:
    known = ["Dia Láctea", "Dia", "Central Lechera Asturiana", "Pascual", "Puleva", "Alpro"]
    normalized = title.lower()
    for brand in known:
        if brand.lower() in normalized:
            return brand
    return None


def _flatten_nutrition(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        flattened: dict[str, object] = {}
        for key, item in value.items():
            if isinstance(item, dict):
                flattened[key] = item.get("value") or item.get("amount") or item.get("name") or str(item)
            else:
                flattened[key] = item
        return flattened
    if isinstance(value, list):
        flattened = {}
        for item in value:
            if isinstance(item, dict):
                label = item.get("name") or item.get("label") or item.get("key")
                amount = item.get("value") or item.get("amount")
                if label and amount:
                    flattened[str(label)] = amount
        return flattened
    return {}














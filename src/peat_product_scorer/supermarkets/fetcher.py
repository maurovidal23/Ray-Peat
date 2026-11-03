from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import Product, SearchResult
from ..nutrition import normalize_nutrition, split_ingredients
from .adapters import SUPPORTED_DOMAINS, supermarket_name_for_url
from .contract import require_evidence, validate_provider_url
from .openfoodfacts import OPENFOODFACTS_PROVIDER
from .openfoodfacts import SOURCE as OPENFOODFACTS_SOURCE
from .parser import parse_product_page

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"}
DIA_BASE = "https://www.dia.es"
MERCADONA_BASE = "https://tienda.mercadona.es"

GENERIC_SEARCH_PROVIDERS = (
    ("Alcampo", "https://www.compraonline.alcampo.es/search?text={query}", "compraonline.alcampo.es"),
    ("Consum", "https://tienda.consum.es/es/search?text={query}", "tienda.consum.es"),
    ("Eroski", "https://supermercado.eroski.es/es/search/results/?q={query}", "supermercado.eroski.es"),
)


RELIABLE_SEARCH_PROVIDERS = (
    "Mercadona",
    "DIA",
    "Alcampo",
    "Consum",
    "Eroski",
    OPENFOODFACTS_SOURCE,
)
MAX_RESULTS_PER_PROVIDER = 50
MAX_CONCURRENT_SEARCHES = 4
MAX_PRODUCT_REDIRECTS = 5
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


def search_products(
    query: str,
    max_results: int = 10,
    providers: list[str] | None = None,
) -> list[SearchResult]:
    query = _normalize_search_query(query)
    max_results = max(0, min(max_results, MAX_RESULTS_PER_PROVIDER))
    if not max_results:
        return []
    per_source = max_results
    selected = _normalize_provider_filter(providers)
    # The default/"all" view intentionally uses only providers whose result links
    # are known to be fetchable. Less reliable providers remain available when
    # explicitly requested by name.
    default_sources = set(RELIABLE_SEARCH_PROVIDERS)
    searches: list[tuple[str, Any]] = []
    if _provider_selected("DIA", selected) and (selected is not None or "DIA" in default_sources):
        searches.append(("DIA", lambda: _search_dia(query, per_source)))
    if _provider_selected("Mercadona", selected) and (selected is not None or "Mercadona" in default_sources):
        searches.append(("Mercadona", lambda: _search_mercadona_categories(query, per_source)))
    for source, template, domain in GENERIC_SEARCH_PROVIDERS:
        if not _provider_selected(source, selected):
            continue
        if selected is None and source not in default_sources:
            continue
        searches.append(
            (
                source,
                lambda source=source, template=template, domain=domain: _search_generic_provider(
                    source, template, domain, query, per_source
                ),
            )
        )
    if _provider_selected(OPENFOODFACTS_SOURCE, selected) and (
        selected is not None or OPENFOODFACTS_SOURCE in default_sources
    ):
        searches.append(
            (
                OPENFOODFACTS_SOURCE,
                lambda: _search_openfoodfacts(query, per_source),
            )
        )

    provider_results: list[list[SearchResult]] = [[] for _ in searches]
    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_SEARCHES, len(searches) or 1)) as executor:
        futures = [executor.submit(search) for _, search in searches]
        for index, future in enumerate(futures):
            try:
                provider_results[index] = future.result()
            except Exception:
                provider_results[index] = []
    return _interleave_search_results(provider_results, max_results=max_results)


def _normalize_search_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", query).strip()
    generic_browser_terms = {
        "",
        "none",
        "null",
        "undefined",
        "product",
        "products",
        "producto",
        "productos",
        "best product",
        "best products",
    }
    return "leche" if cleaned.lower() in generic_browser_terms else cleaned


def available_search_providers() -> list[str]:
    # These providers currently expose product links that can be searched and scored reliably.
    return list(RELIABLE_SEARCH_PROVIDERS)


def _normalize_provider_filter(providers: list[str] | None) -> set[str] | None:
    if not providers:
        return None
    normalized = {provider.strip().lower() for provider in providers if provider and provider.strip()}
    normalized.discard("all")
    return normalized or None


def _provider_selected(source: str, selected: set[str] | None) -> bool:
    if selected is None:
        return True
    normalized_source = source.lower()
    return normalized_source in selected


def search_dia_products(query: str, max_results: int = 10) -> list[SearchResult]:
    return list(_search_dia(query, max_results))


def search_mercadona_products(query: str, max_results: int = 10) -> list[SearchResult]:
    return list(_search_mercadona_categories(query, max_results))


def _search_openfoodfacts(query: str, max_results: int) -> list[SearchResult]:
    return OPENFOODFACTS_PROVIDER.search(query, max_results=max_results)


def _fetch_openfoodfacts_product(url: str, timeout: int) -> Product:
    return OPENFOODFACTS_PROVIDER.fetch(url, timeout=timeout)


def _interleave_search_results(
    provider_results: list[list[SearchResult]],
    *,
    max_results: int,
) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    max_len = max((len(items) for items in provider_results), default=0)
    for index in range(max_len):
        for items in provider_results:
            if len(results) >= max_results:
                return results
            if index >= len(items):
                continue
            item = items[index]
            if not item.url or item.url in seen_urls:
                continue
            seen_urls.add(item.url)
            results.append(item)
    return results


def _search_generic_provider(
    source: str,
    search_template: str,
    domain: str,
    query: str,
    max_results: int,
) -> list[SearchResult]:
    search_url = search_template.format(query=requests.utils.quote(query))
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    query_terms = _search_terms(query)
    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    for anchor in soup.select("a[href]"):
        if len(results) >= max_results:
            break
        href = anchor.get("href") or ""
        url = urljoin(search_url, href)
        parsed = urlparse(url)
        if domain not in parsed.netloc.lower():
            continue
        if not _is_productish_url(url, source=source):
            continue
        display_name = _anchor_product_name(anchor) or _name_from_url(url)
        if not _matches_query(display_name, query_terms) and not _matches_query(url, query_terms):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        results.append(
            SearchResult(
                source=source,
                query=query,
                display_name=display_name or "Unnamed product",
                product_id=_product_id_from_url(url),
                url=url,
                brand=None,
                price=None,
                price_currency="EUR",
                thumbnail=_anchor_image(anchor, search_url),
                category=None,
            )
        )
    return results


def _search_terms(query: str) -> list[str]:
    return [term for term in re.split(r"\s+", query.lower().strip()) if len(term) >= 2]


def _matches_query(value: str, query_terms: list[str]) -> bool:
    normalized = value.lower()
    return not query_terms or any(term in normalized for term in query_terms)


def _is_productish_url(url: str, *, source: str) -> bool:
    path = urlparse(url).path.lower()
    negative_markers = ("/search", "/buscar", "/category", "/categoria", "/catalog", "/login", "/cart")
    if any(marker in path for marker in negative_markers):
        return False

    source_markers = {
        "Alcampo": ("/products/",),
        "Consum": ("/p/",),
        "Eroski": ("/productdetail/",),
    }
    markers = source_markers.get(source) or ("/product", "/products", "/producto", "/productdetail", "/p/")
    return any(marker in path for marker in markers)


def _anchor_product_name(anchor: Any) -> str:
    labels = [
        anchor.get("aria-label"),
        anchor.get("title"),
        anchor.get_text(" ", strip=True),
    ]
    img = anchor.find("img")
    if img:
        labels.extend([img.get("alt"), img.get("title")])
    for label in labels:
        if not label:
            continue
        cleaned = re.sub(r"\s+", " ", str(label)).strip()
        normalized = cleaned.lower()
        weak_labels = {
            "none",
            "null",
            "undefined",
            "mostrar todas las opiniones",
            "ver producto",
            "comprar",
            "anadir",
            "a?adir",
            "mas informacion",
            "m?s informaci?n",
        }
        if cleaned and normalized not in weak_labels:
            return cleaned
    return ""


def _anchor_image(anchor: Any, base_url: str) -> str | None:
    img = anchor.find("img")
    if not img:
        return None
    value = img.get("src") or img.get("data-src") or img.get("data-original")
    return urljoin(base_url, value) if value else None


def _name_from_url(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    slug = re.sub(r"\.html?$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"[-_]+", " ", slug)
    return slug.strip().title()


def _product_id_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    match = re.search(r"(?:/p/|/productdetail/|/products?/)([^/?#]+)", path, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return path.split("/")[-1] or url


def _search_dia(query: str, max_results: int) -> list[SearchResult]:
    api_results = _search_dia_api(query, max_results)
    if api_results:
        return api_results
    return _search_dia_page_context(query, max_results)


def _search_dia_api(query: str, max_results: int) -> list[SearchResult]:
    try:
        response = requests.get(
            f"{DIA_BASE}/api/v1/search-back/search",
            params={"q": query},
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []
    return _dia_search_results_from_items(query, payload.get("search_items") or [], max_results)


def _search_dia_page_context(query: str, max_results: int) -> list[SearchResult]:
    search_url = f"{DIA_BASE}/search?q={requests.utils.quote(query)}"
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        context = _load_script_json(soup, "vike_pageContext")
        search_data = (((context or {}).get("INITIAL_STATE") or {}).get("header") or {}).get("searchData") or {}
    except Exception:
        return []
    return _dia_search_results_from_items(query, search_data.get("search_items") or [], max_results)


def _dia_search_results_from_items(query: str, items: list[dict[str, Any]], max_results: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in items:
        if len(results) >= max_results:
            break
        object_id = item.get("object_id") or item.get("sku_id") or ""
        display_name = item.get("display_name") or ""
        raw_url = item.get("url") or ""
        prices = item.get("prices") or {}
        if not object_id or not display_name or not raw_url:
            continue
        product_url = urljoin(DIA_BASE, raw_url)
        results.append(
            SearchResult(
                source="DIA",
                query=query,
                display_name=display_name,
                product_id=str(object_id),
                url=product_url,
                brand=item.get("brand"),
                price=prices.get("price"),
                price_currency=prices.get("currency"),
                thumbnail=urljoin(DIA_BASE, item.get("image") or "") if item.get("image") else None,
                category=item.get("l1_category_description"),
            )
        )
    return results

def _search_mercadona_categories(query: str, max_results: int) -> list[SearchResult]:
    try:
        cat_resp = requests.get(f"{MERCADONA_BASE}/api/categories/", headers=HEADERS, timeout=15)
        cat_resp.raise_for_status()
        categories = cat_resp.json().get("results") or []
    except Exception:
        return []

    query_lower = query.lower()
    results: list[SearchResult] = []
    seen_ids: set[str] = set()

    for section in categories:
        for cat in section.get("categories") or []:
            if len(results) >= max_results:
                break
            cat_id = cat.get("id")
            cat_name = cat.get("name") or ""
            if not _query_matches_category(query_lower, cat_name):
                continue
            try:
                cat_resp = requests.get(f"{MERCADONA_BASE}/api/categories/{cat_id}/", headers=HEADERS, timeout=15)
                cat_resp.raise_for_status()
                cat_data = cat_resp.json()
            except Exception:
                continue
            sub_categories = cat_data.get("categories") or [cat_data]
            for sub in sub_categories:
                if len(results) >= max_results:
                    break
                for product in sub.get("products") or []:
                    if len(results) >= max_results:
                        break
                    pid = product.get("id")
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    display_name = product.get("display_name") or ""
                    if not _matches_all_query_terms(display_name, query_lower):
                        continue
                    url = product.get("share_url") or ""
                    pi = product.get("price_instructions") or {}
                    results.append(
                        SearchResult(
                            source="Mercadona",
                            query=query,
                            display_name=display_name,
                            product_id=str(pid),
                            url=url,
                            brand=cat_name,
                            price=pi.get("bulk_price") or pi.get("unit_price"),
                            price_currency="EUR",
                            thumbnail=product.get("thumbnail"),
                            category=section.get("name"),
                        )
                    )
    return results


def _query_matches_category(query_lower: str, cat_name: str) -> bool:
    cat_lower = cat_name.lower()
    for token in query_lower.split():
        if token in cat_lower:
            return True
    return False


def _matches_all_query_terms(value: str, query: str) -> bool:
    value_lower = value.lower()
    terms = _search_terms(query)
    return not terms or all(term in value_lower for term in terms)


def fetch_product(url: str, timeout: int = 20) -> Product:
    return require_evidence(_fetch_product(url, timeout=timeout))


def _fetch_product(url: str, timeout: int = 20) -> Product:
    if _is_openfoodfacts_url(url):
        return _fetch_openfoodfacts_product(url, timeout=timeout)

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

    response = _get_supported_product_url(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    source = supermarket_name_for_url(url)
    return parse_product_page(response.text, url=url, source=source)


def _is_openfoodfacts_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host == "openfoodfacts.org" or host.endswith(".openfoodfacts.org")


def _get_supported_product_url(
    url: str,
    *,
    headers: dict[str, str],
    timeout: int,
) -> requests.Response:
    """Fetch a supermarket page without allowing redirects to escape the allowlist."""
    current_url = url
    for _ in range(MAX_PRODUCT_REDIRECTS + 1):
        _validate_supported_product_url(current_url)
        response = requests.get(
            current_url,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        if getattr(response, "status_code", 200) not in REDIRECT_STATUS_CODES:
            return response
        location = getattr(response, "headers", {}).get("location")
        if not location:
            response.raise_for_status()
            return response
        current_url = urljoin(current_url, location)
    raise requests.TooManyRedirects(f"Too many redirects while fetching {url!r}")


def _validate_supported_product_url(url: str) -> None:
    validate_provider_url(url, SUPPORTED_DOMAINS)


def _build_product(
    *,
    name: str,
    source: str,
    url: str,
    brand: str | None = None,
    description: str | None = None,
    ingredient_text: str | None = None,
    ingredient_source: str | None = None,
    nutrition_raw: dict[str, object] | None = None,
    raw: dict[str, Any] | None = None,
    fallback: Product | None = None,
) -> Product:
    cleaned_ingredient_text = _standardize_ingredient_text(ingredient_text, name=name, description=description)
    ingredients = _standardize_ingredients(cleaned_ingredient_text)
    if not ingredients and fallback and fallback.ingredients:
        ingredients = fallback.ingredients
        cleaned_ingredient_text = ", ".join(fallback.ingredients)
        ingredient_source = ingredient_source or "generic_parser"

    nutrition = normalize_nutrition(nutrition_raw or {})
    if not nutrition and fallback and fallback.nutrition_per_100g:
        nutrition = fallback.nutrition_per_100g

    missing_fields: list[str] = []
    if not ingredients:
        missing_fields.append("ingredients")
    if not nutrition:
        missing_fields.append("nutrition_per_100g")

    raw_payload = dict(raw or {})
    raw_payload["extraction"] = {
        "ingredient_source": ingredient_source,
        "has_ingredients": bool(ingredients),
        "has_nutrition_per_100g": bool(nutrition),
        "missing_fields": missing_fields,
    }

    return Product(
        name=name,
        source=source,
        url=url,
        brand=brand,
        description=description,
        ingredient_text=cleaned_ingredient_text,
        ingredient_source=ingredient_source,
        ingredients=ingredients,
        nutrition_per_100g=nutrition,
        missing_fields=missing_fields,
        raw=raw_payload,
    )



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

    return _build_product(
        name=payload.get("display_name") or details.get("description") or "Unknown Mercadona product",
        source="Mercadona",
        url=payload.get("share_url") or api_url,
        brand=payload.get("brand") or details.get("brand"),
        description=details.get("description") or details.get("legal_name"),
        ingredient_text=ingredients_text,
        ingredient_source="mercadona.nutrition_information.ingredients" if ingredients_text else None,
        nutrition_raw=_flatten_nutrition(raw_nutrition),
        raw={"mercadona_api": payload},
    )


def _fetch_dia_product(url: str, timeout: int) -> Product:
    product_id = _dia_product_id(url)
    if product_id:
        try:
            return _fetch_dia_api_product(product_id, url=url, timeout=timeout)
        except requests.RequestException:
            pass

    response = _get_supported_product_url(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    context = _load_script_json(soup, "vike_pageContext")
    product = ((context.get("INITIAL_STATE") or {}).get("product") or {}) if context else {}

    if not product:
        return parse_product_page(response.text, url=url, source="DIA")

    return _product_from_dia_payload(product, url=url, raw_key="dia_page_context_product")


def _dia_product_id(url: str) -> str | None:
    match = re.search(r"/p/([^/?#]+)", url)
    return match.group(1) if match else None


def _fetch_dia_api_product(product_id: str, *, url: str, timeout: int) -> Product:
    api_url = f"https://www.dia.es/api/v1/pdp-back/{product_id}"
    parsed = urlparse(url)
    path = parsed.path or f"/p/{product_id}"
    response = requests.get(
        api_url,
        params={"path": path},
        headers={**HEADERS, "Accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    product = payload.get("product") or {}
    if not product:
        raise ValueError("DIA API response did not include product data.")
    return _product_from_dia_payload(product, url=url, raw_key="dia_pdp_api_product")


def _product_from_dia_payload(product: dict[str, Any], *, url: str, raw_key: str) -> Product:
    title = (product.get("primary_info") or {}).get("title") or product.get("sku_id") or "Unknown DIA product"
    ingredients = _strip_html((product.get("ingredients") or {}).get("text") or "")
    nutritional_info = product.get("nutritional_info") or {}
    raw_nutrition = _dia_nutrition(nutritional_info)

    return _build_product(
        name=title,
        source="DIA",
        url=url,
        brand=_dia_brand_from_title(title),
        description=(product.get("product_info") or {}).get("product"),
        ingredient_text=ingredients,
        ingredient_source="dia.ingredients.text" if ingredients else None,
        nutrition_raw=raw_nutrition,
        raw={raw_key: product},
    )


def _fetch_alcampo_product(url: str, timeout: int) -> Product:
    response = _get_supported_product_url(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    generic = parse_product_page(response.text, url=url, source="Alcampo")
    sections = _alcampo_sections(soup)
    nutrition = _table_to_mapping(sections.get("Datos nutricionales"))
    characteristics = _table_to_mapping(sections.get("Características"))
    ingredients = sections.get("Ingredientes") or ""
    brand = sections.get("Marca")

    return _build_product(
        name=generic.name,
        source="Alcampo",
        url=url,
        brand=brand,
        description=(
            characteristics.get("Denominaci\u00f3n legal del alimento")
            or characteristics.get("Denominaci?n legal del alimento")
            or generic.description
        ),
        ingredient_text=ingredients,
        ingredient_source="alcampo.sections.Ingredientes" if ingredients else None,
        nutrition_raw=nutrition,
        raw={"alcampo_sections": sections, "json_ld": generic.raw.get("json_ld")},
        fallback=generic,
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
    ingredient_text = _consum_ingredient_text(product_data)

    return _build_product(
        name=name,
        source="Consum",
        url=product_data.get("url") or api_url,
        brand=brand.get("name") if isinstance(brand, dict) else None,
        description=description,
        ingredient_text=ingredient_text,
        ingredient_source="consum.attributeGroups.ingredients" if ingredient_text else None,
        nutrition_raw=_consum_nutrition(product_data),
        raw={"consum_api": payload},
    )


def _consum_ingredient_text(product_data: dict[str, Any]) -> str:
    values: list[str] = []
    ingredient_markers = ("ingred", "ingredient", "compos", "composition")
    for group in product_data.get("attributeGroups") or []:
        group_label = f"{group.get('name') or ''} {group.get('code') or ''}".lower()
        for attribute in group.get("attributes") or []:
            code = str(attribute.get("code") or "").lower()
            name = str(attribute.get("name") or "").lower()
            label = f"{group_label} {code} {name}"
            if code.startswith("hidden.") or code.startswith("filter."):
                continue
            if not any(marker in label for marker in ingredient_markers):
                continue
            for language in attribute.get("languages") or []:
                for value in language.get("values") or []:
                    if isinstance(value, str) and value.strip():
                        values.append(value.strip())
    return " ".join(values)


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
    response = _get_supported_product_url(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    generic = parse_product_page(response.text, url=url, source="Eroski")
    ingredients = _eroski_feature_text(soup, "Ingredientes")
    nutrition = _eroski_nutrition(soup)
    brand = _eroski_brand(generic.name)

    return _build_product(
        name=generic.name,
        source="Eroski",
        url=url,
        brand=brand,
        description=generic.description,
        ingredient_text=ingredients,
        ingredient_source="eroski.feature.Ingredientes" if ingredients else None,
        nutrition_raw=nutrition,
        raw={"json_ld": generic.raw.get("json_ld"), "eroski_nutrition": nutrition},
        fallback=generic,
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


def _standardize_ingredient_text(value: str | None, *, name: str, description: str | None) -> str | None:
    if not value:
        return None
    cleaned = _clean_ingredient_prefix(_strip_html(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return None
    normalized_cleaned = _normalize_compare(cleaned)
    weak_values = {_normalize_compare(name)}
    if description:
        weak_values.add(_normalize_compare(description))
    # Product titles/descriptions are not ingredient evidence.
    if normalized_cleaned in weak_values:
        return None
    return cleaned


def _standardize_ingredients(value: str | None) -> list[str]:
    ingredients = split_ingredients(value)
    result: list[str] = []
    seen: set[str] = set()
    for ingredient in ingredients:
        ingredient = re.sub(r"\s+", " ", ingredient).strip(" .")
        if not ingredient:
            continue
        key = _normalize_compare(ingredient)
        if key in seen:
            continue
        seen.add(key)
        result.append(ingredient)
    return result


def _normalize_compare(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()



def _strip_html(value: str) -> str:
    value = html.unescape(value)
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














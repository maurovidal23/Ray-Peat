from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import (
    Product,
    ProviderOutcome,
    ProviderSearchOutcome,
    SearchResult,
    SearchResults,
)
from ..nutrition import normalize_nutrition, split_ingredients
from .adapters import SUPPORTED_DOMAINS, supermarket_name_for_url
from .contract import (
    blocked_cause_for_response,
    classify_provider_failure,
    require_evidence,
    validate_provider_url,
)
from .parser import parse_product_page

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9"}

GENERIC_SEARCH_PROVIDERS = (
    ("Eroski", "https://supermercado.eroski.es/es/search/results/?q={query}", "supermercado.eroski.es"),
)


RELIABLE_SEARCH_PROVIDERS = ("Eroski",)
MAX_RESULTS_PER_PROVIDER = 50
MAX_CONCURRENT_SEARCHES = 4
MAX_PRODUCT_REDIRECTS = 5
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


def search_products(
    query: str,
    max_results: int = 10,
    providers: list[str] | None = None,
) -> SearchResults:
    query = _normalize_search_query(query)
    max_results = max(0, min(max_results, MAX_RESULTS_PER_PROVIDER))
    if not max_results:
        return SearchResults()
    per_source = max_results
    selected = _normalize_provider_filter(providers)
    # The default/"all" view intentionally uses only providers whose result links
    # are known to be fetchable.
    default_sources = set(RELIABLE_SEARCH_PROVIDERS)
    searches: list[tuple[str, Any]] = []
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

    provider_results: list[list[SearchResult]] = []
    provider_status: list[ProviderOutcome] = []
    with ThreadPoolExecutor(max_workers=min(MAX_CONCURRENT_SEARCHES, len(searches) or 1)) as executor:
        futures = [executor.submit(search) for _, search in searches]
        for (provider, _), future in zip(searches, futures):
            try:
                outcome = _as_provider_outcome(provider, future.result())
            except Exception as exc:
                outcome = _failure_outcome(provider, exc)
            provider_results.append(list(outcome))
            provider_status.append(outcome.status())
    return SearchResults(
        _interleave_search_results(provider_results, max_results=max_results),
        provider_status=provider_status,
    )


def _as_provider_outcome(provider: str, value: Any) -> ProviderSearchOutcome:
    if isinstance(value, ProviderSearchOutcome):
        return value
    results = list(value or [])
    return ProviderSearchOutcome(
        results,
        provider=provider,
        outcome="ok" if results else "empty",
        products=len(results),
    )


def _failure_outcome(
    provider: str,
    error: BaseException,
    *,
    response: object | None = None,
) -> ProviderSearchOutcome:
    outcome, cause = classify_provider_failure(error, response=response)
    return ProviderSearchOutcome([], provider=provider, outcome=outcome, products=0, cause=cause)


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
) -> ProviderSearchOutcome:
    search_url = search_template.format(query=requests.utils.quote(query))
    response = None
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        return _failure_outcome(
            source,
            exc,
            response=getattr(exc, "response", None) or response,
        )

    blocked_cause = blocked_cause_for_response(response)
    if blocked_cause:
        return ProviderSearchOutcome(
            [],
            provider=source,
            outcome="blocked",
            products=0,
            cause=blocked_cause,
        )

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
    return ProviderSearchOutcome(
        results,
        provider=source,
        outcome="ok" if results else "empty",
        products=len(results),
    )


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
    match = re.search(r"(?:/productdetail/|/products?/)([^/?#]+)", path, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return path.split("/")[-1] or url


def fetch_product(url: str, timeout: int = 20) -> Product:
    return require_evidence(_fetch_product(url, timeout=timeout))


def _fetch_product(url: str, timeout: int = 20) -> Product:
    if "supermercado.eroski.es" in url and "/productdetail/" in url:
        return _fetch_eroski_product(url, timeout=timeout)

    response = _get_supported_product_url(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    source = supermarket_name_for_url(url)
    return parse_product_page(response.text, url=url, source=source)


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

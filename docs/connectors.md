# Supermarket Connectors

This document describes the connectors that ship with Ray Peat Product Scorer,
the strict contract they must satisfy, and the stores that were explored but
removed because they could not meet that contract.

> **Live audit (2026-11-04):** the current adapter registry was audited against
> live provider responses. DIA, Eroski, and Open Food Facts produced scoreable
> evidence; Mercadona, Alcampo, and Consum failed and are flagged for removal in
> issue #16. The full status table, evidence snippets, and keep/remove decision
> live in [Provider audit](./provider_audit.md).

## Shared provider contract

The connector layer applies one contract across all registered providers. The
`ProductProvider` abstraction defines:

- `search(query, max_results)` returns `SearchResult` links and display metadata.
  Search metadata is never scored by itself.
- `fetch(url, timeout)` returns a normalized `Product`.
- `fetch_and_validate(url, timeout)` rejects URLs outside the provider's allowed
  domains and then requires complete product evidence before returning.

Open Food Facts implements `ProductProvider` directly. The supermarket connectors
are dispatched through `fetcher.py` and are validated by the same URL and
evidence checks before they return a product.

The evidence guardrail is intentionally strict:

- `ingredients` must contain at least one non-blank ingredient.
- At least **four of six** normalized nutrient keys must be present and finite:
  `sugars_g`, `protein_g`, `fat_g`, `saturated_fat_g`, `salt_g`, and `carbs_g`.
- Missing, blank, non-numeric, `NaN`, and infinite values do not count as
  evidence. Zero is a valid value.
- Guardrail keys are matched exactly. In particular, total carbohydrate stored
  as `carbohydrate_g` does not satisfy the `carbs_g` slot. Open Food Facts maps
  `carbohydrates_100g` to both keys explicitly.

The product-URL guardrail applies before fetch where a URL is accepted from a
user:

- The URL must use HTTP or HTTPS, include a hostname, and belong to a verified
  provider domain or one of its subdomains.
- Credentials, IP addresses, nonstandard ports, and deceptive domain suffixes
  are rejected.
- Redirects are checked against the same allowlist and are capped at five hops.

If a fetched product fails the evidence guardrail, the API returns an evidence
error instead of a score. In search results, the row is kept visible with no
`score` and an explanatory `error`.

### Metadata-fallback scoring is removed

Earlier versions could score a search result from its title, category, price,
and other tile metadata when the product could not be fetched. That fallback has
been removed. A score is produced only from a fetched product that satisfies the
ingredients and nutrition guardrail. Tiles without fetchable evidence remain
unscored and sort after scored products.

## Registered provider contracts

| Provider | Allowed domains | Search | Fetch | Guardrail |
| --- | --- | --- | --- | --- |
| **Mercadona** | `mercadona.es` | Walks `/api/categories/` and category product lists, matching query tokens against category names and then all query terms against product display names. No free-text search endpoint is used. | Reads `https://tienda.mercadona.es/api/products/{id}`. Ingredients come from `nutrition_information.ingredients`; nutrition comes from `nutrition_information.nutrition_values` or `values`. | URL allowlist plus shared ingredients and 4-of-6 nutrient evidence check. |
| **DIA** | `dia.es` | Calls `/api/v1/search-back/search?q={query}`. If that yields nothing, reads the server-rendered `/search?q={query}` page and its `vike_pageContext` search data. | Tries `/api/v1/pdp-back/{id}?path={product_path}`. If that fails, reads `vike_pageContext` from the product page, then falls back to the generic HTML/JSON-LD parser. Ingredients come from `dia.ingredients.text`; nutrition comes from `nutritional_info.nutritional_values`. | URL allowlist plus shared ingredients and 4-of-6 nutrient evidence check. |
| **Alcampo** | `alcampo.es` | Reads `https://www.compraonline.alcampo.es/search?text={query}` and extracts matching `/products/` links. | Reads the server-rendered product page and its `Ingredientes`, `Datos nutricionales`, and `Características` sections. Falls back to the generic HTML/JSON-LD parser for missing product fields. Ingredients come from the `Ingredientes` section. | URL allowlist, redirect checks, plus shared ingredients and 4-of-6 nutrient evidence check. |
| **Consum** | `consum.es` | Reads `https://tienda.consum.es/es/search?text={query}` and extracts matching `/p/` links. | Reads `https://tienda.consum.es/api/rest/V1.0/catalog/product/code/{code}`. Ingredients come from ingredient-labeled attribute groups; nutrition comes from nutrient/value attribute groups. | URL allowlist plus shared ingredients and 4-of-6 nutrient evidence check. |
| **Eroski** | `eroski.es` | Reads `https://supermercado.eroski.es/es/search/results/?q={query}` and extracts matching `/productdetail/` links. | Reads the server-rendered product detail page, its `Ingredientes` feature, and its nutrition feature. Falls back to the generic HTML/JSON-LD parser for missing product fields. | URL allowlist, redirect checks, plus shared ingredients and 4-of-6 nutrient evidence check. |
| **Open Food Facts** | `openfoodfacts.org`, `world.openfoodfacts.org` | Calls `/api/v2/search` with `search_terms`, `countries_tags_en=spain`, a page size, and an explicit field list. Each candidate is converted and checked against the evidence guardrail before it is returned, so incomplete products are dropped from search results. | Reads `/api/v2/product/{code}` for URLs of the form `/product/{code}`. Ingredients come from `ingredients_text_es`; nutriments are mapped to normalized keys, including `carbohydrates_100g` → `carbohydrate_g` and `carbs_g`. | URL allowlist plus shared ingredients and 4-of-6 nutrient evidence check, applied before search results are exposed and again on fetch. |

The default **All providers** search queries only this registered set:
**Mercadona**, **DIA**, **Alcampo**, **Consum**, **Eroski**, and **Open Food
Facts**. Individual registered providers can be selected by name. Removed
providers are not available, even when requested explicitly. The contracts in
the table describe the implemented adapters; they are not a live availability
guarantee. See [Provider audit](./provider_audit.md) for the 2026-11-04 results.

## Removed providers

These stores were removed from the adapter registry, search defaults, and
`/api/connectors`. Their URLs no longer pass the product-URL allowlist, so they
are rejected with an evidence/URL error instead of being scraped through a
generic fallback.

| Provider | Domains | Guardrail reason for removal |
| --- | --- | --- |
| **Bon Preu / Esclat** | `bonpreuesclat.cat`, `compraonline.bonpreuesclat.cat` | The partial connector exposed identity, brand, category, size, image, and price but not ingredients or nutrition. Without ingredients and at least four guardrail nutrients it could never provide scoreable evidence. |
| **Carrefour España** | `carrefour.es` | Simple unauthenticated requests return `403 Forbidden` before app/API product data is available, so no verified fetch path can supply the required evidence. |
| **El Corte Inglés** | `elcorteingles.es` | Akamai returns access denied for simple unauthenticated requests, blocking the evidence required by the guardrail. |
| **Lidl Spain** | `lidl.es` | The connection terminates unexpectedly from this environment before product data can be inspected, so no evidence path could be verified. |
| **Aldi ES** | `aldi.es` | The site is primarily a brochure/catalog without a persistent product-detail API. Known product URL patterns returned 404 and no ingredients/nutrition evidence could be fetched. |
| **Spar ES** | `spar.es` | The reachable site is corporate with no online store or product evidence path. |
| **Hipercor** | `hipercor.es` | `403 Forbidden` from the same Akamai protection as El Corte Inglés. |
| **Gadis Online** | `gadisonline.com` | Connection timeout/no response from this environment, so no evidence could be verified. |
| **Covirán** | `coviransupermercados.com` | Connection timeout/no response from this environment, so no evidence could be verified. |
| **Caprabo** | `caprabo.com` | `403 Forbidden` behind a WAF; no bypass was attempted. |
| **Condis** | `condis.es` | Connection timeout/no response from this environment, so no evidence could be verified. |
| **Froiz** | `froiz.es` | Connection timeout/no response from this environment, so no evidence could be verified. |

## Exploration notes for blocked stores

The notes below are retained from the provider exploration work. They are
historical research context, not active connectors.

### Carrefour Spain
- **Status**: Not connected. Simple unauthenticated requests from this environment return `403 Forbidden` before app/API data is available.
- **Guardrail reason**: No verified product-data path can supply ingredients plus at least four guardrail nutrients.

### El Corte Inglés Supermercado
- **Status**: Not connected. Akamai returns access denied for simple unauthenticated requests.
- **Guardrail reason**: The blocked product pages cannot supply the required evidence.

### Lidl Spain
- **Status**: Not connected. The connection terminates unexpectedly from this environment before product data can be inspected.
- **Guardrail reason**: No product evidence path could be verified.

### Aldi ES (aldi.es)
- **Status**: 200 OK, Next.js SSR app with Magnolia CMS headless backend.
- **Stack**: Next.js with `__NEXT_DATA__` embedded state, Algolia for search (algolia.net/algolianet.com in CSP), Adobe Scene7 (s7g10.scene7.com) for images.
- **Product URLs**: Uses Magnolia content paths (e.g., `/spain/...`). The site is more informational/catalog than transactional online store — no `tienda.` subdomain or shopping cart API was detected.
- **Product pages**: URL pattern unknown — tried `/product.html`, `/leche-entera.html`, `/compra-online/leche-y-huevos/leche.html` all returned 404.
- **Next.js build ID**: `GSFdk_gRuNvb25jWgC1gU`
- **Potential approach**: Inspect `__NEXT_DATA__` on category landing pages (e.g., `/online-shop.html`) for product listings. Search API may be accessible via Algolia or Next.js API routes. Further investigation needed on product detail page URL patterns — the site primarily shows weekly brochures, not a persistent online catalog.

### Bon Preu / Esclat (compraonline.bonpreuesclat.cat)
- **Status**: Removed. Previously added as a native partial connector.
- **Stack**: React with server-side rendered `window.__INITIAL_STATE__` (similar pattern to DIA's `vike_pageContext`). Uses GraphQL for data fetching. AWS WAF protection (challenge.js).
- **Search endpoint**: `/products/search?q={query}` redirected to `/search?q={query}` and returned embedded search state.
- **Product data**: `data.products.productEntities` contained identity fields including `productId`, `retailerProductId`, `name`, `brand`, `categoryPath`, `size`, `image`, and `price`. Search result groups lived under `data.search.catalogue.data.productGroups`.
- **Removed behavior**: Parsed `__INITIAL_STATE__`, preferred exact UUID or retailer product id matches from the URL, and otherwise selected the first non-featured search result. Ingredients and nutrition were not present in the reachable state, so the products could not satisfy the evidence guardrail.
- **Future work**: A conforming connector would need the product detail route or GraphQL persisted query that exposes ingredients and nutrition.

### Spar ES (spar.es)
- **Status**: 301 Moved Permanently -> 200 OK.
- **Notes**: Main corporate site, no online store detected. Not a priority.

### Hipercor (hipercor.es)
- **Status**: 403 Forbidden (same El Corte Inglés group, protected by Akamai).
- **Notes**: Same blocking as El Corte Inglés. No bypass attempted.

### Gadis Online (gadisonline.com)
- **Status**: No response / connection timeout.
- **Notes**: Possibly geo-blocked or requires VPN from Spanish IP.

### Covirán (coviransupermercados.com)
- **Status**: No response / connection timeout.
- **Notes**: Possibly geo-blocked or requires VPN from Spanish IP.

### Caprabo (caprabo.com)
- **Status**: 403 Forbidden.
- **Notes**: Protected by WAF. No bypass attempted.

### Condis (compraonline.condis.es)
- **Status**: No response / connection timeout.
- **Notes**: Possibly geo-blocked.

### Froiz (compraonline.froiz.es)
- **Status**: No response / connection timeout.
- **Notes**: Possibly geo-blocked.

## Open data / alternative sources

### Open Food Facts (world.openfoodfacts.org)
- **Type**: Open collaborative database of food products from around the world.
- **Status**: Active registered provider. Live search is degraded upstream; see [Provider audit](./provider_audit.md).
- **API**: REST API at `/api/v2/product/{code}` and `/api/v2/search`.
- **Spanish coverage**: Contains many Spanish products with `ingredients_text_es`, `nutriments` (nutrition per 100 g), `brands`, and `categories_tags`.
- **Guardrail behavior**: Search candidates are filtered through the evidence guardrail, and fetched products are validated before scoring. Anonymous requests are rate-limited, so a descriptive User-Agent is sent as required by Open Food Facts.
- **Limitations**: Anonymous requests can still be rate-limited or unavailable under load. Bulk data remains freely downloadable for offline workflows.

### BEDCA (Base de Datos Española de Composición de Alimentos)
- **URL**: https://www.bedca.net/
- **Type**: Spanish government food composition database maintained by AESAN (Agencia Española de Seguridad Alimentaria y Nutrición).
- **Data**: Contains nutritional composition data for hundreds of Spanish foods — energy, macronutrients, vitamins, minerals.
- **API**: Not a public REST API — data is accessed via web interface and downloadable files.
- **Potential**: Good for nutritional reference data, but not suitable for real-time product lookup by barcode. Could be used as a static knowledge base for common ingredients.

### AECOC (Asociación Española de Codificación Comercial)
- **URL**: https://www.aecoc.es/
- **Type**: Spanish GS1 member organization that manages barcode standards in Spain.
- **Data**: Barcode registry for Spanish products.
- **Access**: Not publicly available as an API — barcode data requires membership.

## Strategy notes for blocked supermarkets

There is no generic fallback parser for removed providers anymore. To add a
native connector for a blocked store, the provider must first supply ingredients
and at least four of the six guardrail nutrients through a verified data path.
One of these approaches would be needed:

1. **Browser-based scraping**: Use Playwright/Puppeteer/Selenium to load the page with a real browser, bypassing Cloudflare/Akamai JS challenges.
2. **Official partnership**: Request API access through the supermarket's B2B/B2C programs.
3. **Mobile app API reverse engineering**: Inspect network traffic from the supermarket's mobile app (usually less protected than web).
4. **Cached/mirror data**: Use Google Cache, Bing Cache, or third-party aggregators like Open Food Facts.

Once a path is verified, the provider should implement `ProductProvider` and be
added to `ADAPTERS` and the reliable search provider list only after its fetched
products pass the shared guardrail.

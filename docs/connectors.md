# Supermarket Connectors

## Verified live connectors

- **Mercadona**: reads `https://tienda.mercadona.es/api/products/{id}` for product URLs from `tienda.mercadona.es/product/{id}/...`.
- **DIA**: reads the server-rendered `vike_pageContext` JSON from product pages like `https://www.dia.es/.../p/{sku}`.
- **Alcampo**: reads server-rendered product pages from `https://www.compraonline.alcampo.es/products/.../{id}` and extracts ingredient/nutrition tables.
- **Consum**: reads `https://tienda.consum.es/api/rest/V1.0/catalog/product/code/{code}` for product URLs from `https://tienda.consum.es/es/p/.../{code}`.
- **Eroski**: reads product detail pages from `https://supermercado.eroski.es/es/productdetail/.../` and extracts ingredients plus full nutrition lists.
- **Bon Preu / Esclat**: reads server-rendered `window.__INITIAL_STATE__` from `compraonline.bonpreuesclat.cat` pages. Current reachable state provides product identity, brand, category, size, image, and price, but not ingredients or nutrition, so those fields are explicitly marked missing.

## Explored but not connected yet

- **Carrefour Spain**: simple unauthenticated requests from this environment return `403 Forbidden` before app/API data is available.
- **El Corte Ingles Supermercado**: Akamai returns access denied for simple unauthenticated requests.
- **Lidl Spain**: the connection terminates unexpectedly from this environment before product data can be inspected.

The unsupported stores still go through the generic HTML/JSON-LD fallback when a URL is passed to `score-url`. Researched stores are registered as known sources so they are labeled correctly, but they are not marked as native connectors until a live product data path is verified.

## New supermarkets tested (2026-06-29)

### Aldi ES (aldi.es)
- **Status**: 200 OK, Next.js SSR app with Magnolia CMS headless backend.
- **Stack**: Next.js with `__NEXT_DATA__` embedded state, Algolia for search (algolia.net/algolianet.com in CSP), Adobe Scene7 (s7g10.scene7.com) for images.
- **Product URLs**: Uses Magnolia content paths (e.g., `/spain/...`). The site is more informational/catalog than transactional online store — no `tienda.` subdomain or shopping cart API was detected.
- **Product pages**: URL pattern unknown — tried `/product.html`, `/leche-entera.html`, `/compra-online/leche-y-huevos/leche.html` all returned 404.
- **Next.js build ID**: `GSFdk_gRuNvb25jWgC1gU`
- **Potential approach**: Inspect `__NEXT_DATA__` on category landing pages (e.g., `/online-shop.html`) for product listings. Search API may be accessible via Algolia or Next.js API routes. Further investigation needed on product detail page URL patterns — the site primarily shows weekly brochures, not a persistent online catalog.

### Bon Preu / Esclat (compraonline.bonpreuesclat.cat)
- **Status**: Native partial connector added.
- **Stack**: React with server-side rendered `window.__INITIAL_STATE__` (similar pattern to DIA's `vike_pageContext`). Uses GraphQL for data fetching. AWS WAF protection (challenge.js).
- **Search endpoint**: `/products/search?q={query}` redirects to `/search?q={query}` and returns embedded search state.
- **Product data**: `data.products.productEntities` contains product identity fields including `productId`, `retailerProductId`, `name`, `brand`, `categoryPath`, `size`, `image`, and `price`. Search result groups live under `data.search.catalogue.data.productGroups`.
- **Connector behavior**: Parses `__INITIAL_STATE__`, prefers exact UUID or retailer product id matches from the URL, and otherwise selects the first non-featured search result. Ingredients and nutrition were not present in the reachable state and are marked missing instead of inferred.
- **Future work**: Discover the product detail route or GraphQL persisted query that exposes ingredients and nutrition.

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
- **API**: REST API at `/api/v0/product/{barcode}.json` or `/api/v2/product/{barcode}`.
- **Spanish coverage**: Contains many Spanish products with `ingredients_text_es`, `nutriments` (nutrition per 100g), `brands`, and `categories_tags`.
- **Limitations**: Anonymous requests are rate-limited (returned 503/unavailable under load during testing). Registration removes limits. Bulk data is freely downloadable.
- **Potential**: Excellent supplementary source for products not found in supermarket APIs. Can be used as a fallback when barcode is known. Requires API key/user-agent management for reliable production use.

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

For Carrefour, El Corte Inglés, Hipercor, and Lidl — the current generic HTML/JSON-LD fallback parser handles them when a direct product URL is provided by the user. To build a native connector, one of these approaches would be needed:

1. **Browser-based scraping**: Use Playwright/Puppeteer/Selenium to load the page with a real browser, bypassing Cloudflare/Akamai JS challenges.
2. **Official partnership**: Request API access through the supermarket's B2B/B2C programs.
3. **Mobile app API reverse engineering**: Inspect network traffic from the supermarket's mobile app (usually less protected than web).
4. **Cached/mirror data**: Use Google Cache, Bing Cache, or third-party aggregators like Open Food Facts.

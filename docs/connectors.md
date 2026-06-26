# Supermarket Connectors

Verified live connectors:

- Mercadona: reads `https://tienda.mercadona.es/api/products/{id}` for product URLs from `tienda.mercadona.es/product/{id}/...`.
- DIA: reads the server-rendered `vike_pageContext` JSON from product pages like `https://www.dia.es/.../p/{sku}`.
- Alcampo: reads server-rendered product pages from `https://www.compraonline.alcampo.es/products/.../{id}` and extracts ingredient/nutrition tables.
- Consum: reads `https://tienda.consum.es/api/rest/V1.0/catalog/product/code/{code}` for product URLs from `https://tienda.consum.es/es/p/.../{code}`.
- Eroski: reads product detail pages from `https://supermercado.eroski.es/es/productdetail/.../` and extracts ingredients plus full nutrition lists.

Explored but not connected yet:

- Carrefour Spain: simple unauthenticated requests from this environment return `403 Forbidden` before app/API data is available.
- El Corte Ingles Supermercado: Akamai returns access denied for simple unauthenticated requests.
- Lidl Spain: the connection terminates unexpectedly from this environment before product data can be inspected.

The unsupported stores still go through the generic HTML/JSON-LD fallback when a URL is passed to `score-url`, but they are not marked as native connectors until a live product data path is verified.

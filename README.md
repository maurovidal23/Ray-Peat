# Ray Peat Product Scorer

MVP for collecting product nutrition data from Spanish online supermarkets and
the Open Food Facts database, then scoring products through a Ray Peat-inspired
nutrition lens.

This is not medical advice. Ray Peat's writing is not the same as mainstream
nutrition guidance, and the score is an explainable heuristic based on a
configurable knowledge base.

## What It Does

- Extracts product title, ingredient text, nutrition values, and product
  metadata from supported supermarket product pages and the Open Food Facts API.
- Normalizes common Spanish nutrition labels such as `grasas`, `hidratos de
  carbono`, `azucares`, `sal`, and `proteinas`.
- Enforces a strict provider evidence contract before scoring: a product must
  expose non-empty ingredients and at least four of the six guardrail nutrients
  (`sugars_g`, `protein_g`, `fat_g`, `saturated_fat_g`, `salt_g`, `carbs_g`).
  Search-result metadata is never turned into a score when product evidence is
  missing.
- Applies a Ray Peat-style rule set focused on PUFA oils, dairy/fruit sugars,
  calcium/phosphorus balance, additives, fortified iron, gums, starch load, and
  protein quality.
- Returns a numeric score plus a human-readable comment, per-component score
  breakdown, confidence, and warnings.
- Serves a searchable Ray Peat article reader generated from
  `maurovidal23/RAY_PEAT` PDF files, with formatted in-app reading instead of
  raw PDFs.

## Supermarket Connectors

Verified native connectors:

- Mercadona: product API at `https://tienda.mercadona.es/api/products/{id}`.
- DIA: product API and server-rendered product JSON in `vike_pageContext`.
- Alcampo: server-rendered product pages with ingredient and nutrition tables.
- Consum: product API at `https://tienda.consum.es/api/rest/V1.0/catalog/product/code/{code}`.
- Eroski: server-rendered product pages with ingredients and full nutrition lists.
- Open Food Facts: API v2 product and search endpoints at `https://world.openfoodfacts.org/api/v2/`.

The default **All providers** search queries only this verified set. Each
provider supports search, fetch, and the shared URL/evidence guardrail described
in `docs/connectors.md`. Non-conforming providers are not available, even when
requested explicitly by name. That document also lists removed providers, the
guardrail reasons for their removal, and exploration notes for blocked stores.

## Quick Start

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Evaluate a product JSON file:

```bash
python -m peat_product_scorer score-file examples/sample_product.json
```

Fetch and evaluate a live product URL from any verified provider:

```bash
python -m peat_product_scorer score-url "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"
python -m peat_product_scorer score-url "https://www.compraonline.alcampo.es/products/auchan-leche-entera-de-vaca-6-x-1-l-producto-alcampo/54178"
python -m peat_product_scorer score-url "https://tienda.mercadona.es/product/4040/aceite-girasol-refinado-02o-hacendado-botella"
python -m peat_product_scorer score-url "https://tienda.consum.es/es/p/aceite-de-girasol-alto-oleico/7299873"
python -m peat_product_scorer score-url "https://supermercado.eroski.es/es/productdetail/18672295-leche-entera-del-pais-vasco-eroski-brik-1-litro/"
python -m peat_product_scorer score-url "https://world.openfoodfacts.org/product/3017620422003"
```

Run the test suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
```

## Scoring

The scoring explanation lives on the main page at `/` in English and at
`/method-es` in Spanish. It documents the component weights, the knowledge-base
rule table, score bands, confidence, and the provider guardrail. `/method` serves
the same English page as `/`.

Search-result metadata (title, category, price, thumbnail) is display-only. A
product is scored only after its fetched ingredients and nutrition satisfy the
evidence guardrail; otherwise the result is shown as unscored with the missing
evidence reported.

## Project Layout

```text
src/peat_product_scorer/
  cli.py                 Command line interface
  models.py              Shared product and score models
  scorer.py              Rule-based scoring engine
  knowledge_base.py      YAML knowledge-base loader
  nutrition.py           Spanish nutrition parsing helpers
  web_app.py             FastAPI pages and JSON API
  static/
    method/              Bilingual methodology pages served at / and /method-es
    library/             Article library pages served at /articles and /articles-es
    index.html           Evaluator and best-products app shell
  supermarkets/
    contract.py          Shared provider, URL, and evidence guardrail contract
    adapters.py          Verified provider registry
    fetcher.py           Search and fetch dispatch for supermarket providers
    openfoodfacts.py     Open Food Facts API v2 provider
    parser.py            Generic HTML/JSON-LD product page parser
data/knowledge/
  ray_peat_rules.yaml    Configurable rule knowledge base
docs/
  connectors.md          Provider contracts, removed providers, exploration notes
examples/
  sample_product.json
tests/
```

## Next Useful Steps

1. Store scraped products in SQLite or Postgres with source URL and scrape timestamp.
2. Add citations and confidence levels to each rule in `data/knowledge/ray_peat_rules.yaml`.
3. Expand provider coverage only where a store can satisfy the strict provider evidence contract.

## Web App and API

Run the local web service:

```bash
uvicorn peat_product_scorer.web_app:app --host 127.0.0.1 --port 8090
```

Pages:

- `/` serves the English bilingual methodology page (the scoring explanation).
- `/method` serves the same English methodology page.
- `/method-es` serves the Spanish methodology page.
- `/evaluator` serves the URL/product evaluator.
- `/products` serves the searchable best-products view.
- `/articles` and `/articles-es` serve the English and Spanish article libraries.
- `/articles/{article_id}` and `/articles-es/{article_id}` redirect to the
  matching article in the library.

API endpoints:

- `GET /health` returns service status, version, and connector names.
- `GET /api/version` returns the package version and build label.
- `GET /api/connectors` returns the verified connectors and their allowed domains.
- `GET /api/search-providers` returns `all` plus the verified search providers.
- `POST /api/search` searches verified providers and returns product links plus a
  per-provider `provider_status` summary.
- `POST /api/search-score` searches, fetches, and scores only products that pass
  the evidence guardrail; unscored rows include an `error` and no `score`. Its
  response also includes `provider_status`. The legacy `/api/search-and-score`
  alias accepts the same request.
- `GET /api/articles` returns PDF-derived paper summaries and language availability.
- `GET /api/articles/{article_id}?lang=en|es` returns formatted paragraphs extracted from the selected PDF variant.
- `POST /api/score` scores either `{ "url": "..." }` or `{ "product": { ... } }`.

Both search endpoints return a `provider_status` list so blocked, failing, or
empty providers are visible instead of looking like "no products found":

```json
[
  {"provider": "DIA", "outcome": "ok", "products": 10},
  {"provider": "Mercadona", "outcome": "blocked", "products": 0, "cause": "HTTP 403"}
]
```

`outcome` is one of `ok`, `empty`, `blocked` (HTTP 403/429 or a captcha/anti-bot
page), or `error` (another exception). `products` counts products available to
the scoring pipeline: search results for `/api/search`, and products that were
fetched and passed the evidence guardrail for `/api/search-score`. A `cause` is
included for non-`ok` outcomes; an `ok` outcome may also carry a `cause` when
some provider categories failed but others still returned usable products
(reported as `partial failure: ...`). Failed providers are excluded from scored
rows but always appear in the summary.

Product payloads returned by the scoring API expose standardized source quality fields:

- `ingredient_text`: cleaned ingredient text before splitting.
- `ingredient_source`: connector field used for ingredients, such as `dia.ingredients.text`.
- `ingredients`: normalized ingredient list.
- `missing_fields`: reports `ingredients` and/or `nutrition_per_100g` when the source did not expose reliable data.

Provider-fed payloads (`url` present, or `source` matching a verified provider)
must satisfy the evidence guardrail and otherwise return HTTP 422. Manual
payloads are still scored, with warnings for missing evidence. Connectors should
not fill `ingredients` from product names or generic descriptions. If a source
does not expose ingredients, leave the list empty and report it in
`missing_fields`.

Example API request:

```bash
curl -X POST http://127.0.0.1:8090/api/score \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"}'
```

## Deployment Shape

The project includes a nan.builders-friendly web service structure:

- `Dockerfile` runs `uvicorn peat_product_scorer.web_app:app` on `${PORT:-8090}`.
- `Procfile` supports Python buildpack-style platforms that inject `$PORT`.
- `requirements.txt` installs the local package and dependencies.
- `/health` is ready for platform health checks.

If the deployment platform stores the knowledge rules outside the repository, set `PEAT_KNOWLEDGE_PATH` to the YAML file path. Otherwise the included `data/knowledge/ray_peat_rules.yaml` is used.

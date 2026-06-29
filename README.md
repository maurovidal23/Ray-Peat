# Ray Peat Product Scorer

MVP for collecting product nutrition data from Spanish online supermarkets and scoring products through a Ray Peat-inspired nutrition lens.

This is not medical advice. Ray Peat's writing is not the same as mainstream nutrition guidance, and the score is an explainable heuristic based on a configurable knowledge base.

## What It Does

- Extracts product title, ingredients, nutrition, and product metadata from supermarket product pages.
- Normalizes common Spanish nutrition labels such as `grasas`, `hidratos de carbono`, `azucares`, `sal`, and `proteinas`.
- Applies a Ray Peat-style rule set focused on PUFA oils, dairy/fruit sugars, calcium/phosphorus balance, additives, fortified iron, gums, starch load, and protein quality.
- Returns a numeric score plus a human-readable comment written as if an evaluator were reviewing the product.
- Serves a searchable Ray Peat article reader generated from `maurovidal23/RAY_PEAT` PDF files, with formatted in-app reading instead of raw PDFs.

## Supermarket Connectors

Verified native connectors:

- Mercadona: product API at `https://tienda.mercadona.es/api/products/{id}`.
- DIA: server-rendered product JSON in `vike_pageContext`.
- Alcampo: server-rendered product pages with ingredient and nutrition tables.
- Consum: product API at `https://tienda.consum.es/api/rest/V1.0/catalog/product/code/{code}`.
- Eroski: server-rendered product pages with ingredients and full nutrition lists.

Generic fallback targets:

- Carrefour Spain
- El Corte Ingles / Supermercado
- Lidl Spain

See `docs/connectors.md` for the current exploration status.

## Quick Start

```powershell
cd ray-peat-product-scorer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Evaluate a product JSON file:

```powershell
python -m peat_product_scorer score-file examples/sample_product.json
```

Fetch and evaluate a live supermarket URL:

```powershell
python -m peat_product_scorer score-url "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"
python -m peat_product_scorer score-url "https://www.compraonline.alcampo.es/products/auchan-leche-entera-de-vaca-6-x-1-l-producto-alcampo/54178"
python -m peat_product_scorer score-url "https://tienda.mercadona.es/product/4040/aceite-girasol-refinado-02o-hacendado-botella"
python -m peat_product_scorer score-url "https://tienda.consum.es/es/p/aceite-de-girasol-alto-oleico/7299873"
python -m peat_product_scorer score-url "https://supermercado.eroski.es/es/productdetail/18672295-leche-entera-del-pais-vasco-eroski-brik-1-litro/"
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Project Layout

```text
src/peat_product_scorer/
  cli.py                 Command line interface
  models.py              Shared product and score models
  scorer.py              Rule-based scoring engine
  knowledge_base.py      YAML knowledge-base loader
  nutrition.py           Spanish nutrition parsing helpers
  supermarkets/          Supermarket connectors and generic page parser
data/knowledge/
  ray_peat_rules.yaml    Configurable rule knowledge base
docs/
  connectors.md          Connector status and exploration notes
examples/
  sample_product.json
tests/
```

## Next Useful Steps

1. Add search commands for connected supermarkets so a user can search by product name before scoring from the web UI.
2. Store scraped products in SQLite or Postgres with source URL and scrape timestamp.
3. Add citations and confidence levels to each rule in `data/knowledge/ray_peat_rules.yaml`.

## Web App and API

Run the local web service:

```powershell
uvicorn peat_product_scorer.web_app:app --host 127.0.0.1 --port 8090
```

Open `http://127.0.0.1:8090` to browse the article library or switch to the evaluator to score a supermarket URL / product JSON payload.

API endpoints:

- `GET /health` returns service status for deployment health checks.
- `GET /api/connectors` returns verified and fallback supermarket connectors.
- `GET /api/articles` returns PDF-derived paper summaries and language availability.
- `GET /api/articles/{article_id}?lang=en|es` returns formatted paragraphs extracted from the selected PDF variant.
- `POST /api/score` scores either `{ "url": "..." }` or `{ "product": { ... } }`.

Product payloads returned by the scoring API now expose standardized source quality fields:

- `ingredient_text`: cleaned ingredient text before splitting.
- `ingredient_source`: connector field used for ingredients, such as `dia.ingredients.text`.
- `ingredients`: normalized ingredient list.
- `missing_fields`: currently reports `ingredients` and/or `nutrition_per_100g` when the source did not expose reliable data.

Connectors should not fill `ingredients` from product names or generic descriptions. If a source does not expose ingredients, leave the list empty and report it in `missing_fields`.

Example API request:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8090/api/score -Method POST -ContentType application/json -Body '{"url":"https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"}'
```

## Deployment Shape

The project includes a nan.builders-friendly web service structure:

- `Dockerfile` runs `uvicorn peat_product_scorer.web_app:app` on `${PORT:-8090}`.
- `Procfile` supports Python buildpack-style platforms that inject `$PORT`.
- `requirements.txt` installs the local package and dependencies.
- `/health` is ready for platform health checks.

If the deployment platform stores the knowledge rules outside the repository, set `PEAT_KNOWLEDGE_PATH` to the YAML file path. Otherwise the included `data/knowledge/ray_peat_rules.yaml` is used.


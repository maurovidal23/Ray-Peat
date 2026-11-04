# Provider audit — 2026-11-04

This document records an end-to-end audit of every supermarket provider named
in issue #15 plus Open Food Facts. The audit ran against the current registered
adapter registry (`src/peat_product_scorer/supermarkets/adapters.py`) using live
network requests from the maintainer checkout on **2026-11-04**. The results
below are evidence from those live runs, not a restatement of the earlier
exploration notes.

A provider is marked **working** only when a real query returns multiple
products whose fetched page supplies non-empty `ingredients` and at least four
of the six guardrail nutrients. A provider that searches but cannot fetch
scoreable evidence is **broken**. The evidence guardrail was not relaxed for
this audit.

## Status table

| Provider | Search works? | Fetch works? | Ingredients? | Nutrition per 100 g? | Verdict | Failure cause | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **DIA** | Yes (5/5 for `leche`, 5/5 for `yogur`) | Yes (5/5 fetched) | Yes | Yes (7–8 keys; 4-of-6 guardrail passes) | **working** | — | `search-score "leche" --source DIA` → scores 78–80; `score-url` README milk URL → 80/100 |
| **Eroski** | Yes (5/5 for `leche`, 5/5 for `yogur`) | Yes (5/5 fetched) | Yes | Yes (7–8 keys; 4-of-6 guardrail passes) | **working** | — | `search-score "leche" --source Eroski` → 78; `search-score "yogur" --source Eroski` → 76; `score-url` README milk URL → 78/100 |
| **Open Food Facts** | Partial: evidence-conforming results, but the upstream search page ignores query semantics and intermittently returns `503` | Yes (5/5 fetched when search succeeds) | Yes | Yes (8–9 keys; guardrail passes) | **working\*** | Upstream `/api/v2/search` returned the same generic catalogue page for `leche` and `yogur`, and `503 Page temporarily unavailable` on some attempts. Product URLs still fetch scoreable evidence. | `search-score "leche" --source "Open Food Facts"` → scores 42–70 for unrelated products; `score-url` Nutella barcode → 42/100 |
| **Mercadona** | Yes (5/5 for both queries) | **No** | Yes | **No** | **broken** | Product API schema change: `/api/products/{id}` now exposes `nutrition_information` containing only `allergens` and `ingredients`. All six guardrail nutrients are absent, so no product can be scored. | `search-score "leche" --source Mercadona` → 5 rows, all `Mercadona evidence incomplete: missing sugars_g, protein_g, fat_g, saturated_fat_g, salt_g, carbs_g` |
| **Alcampo** | **No** (0 results) | **No** | No | No | **broken** | AWS WAF challenge blocks search and product pages (`x-amzn-waf-action: challenge`, HTTP 202/302/403 depending on headers). A transient earlier search result also lacked every guardrail nutrient. | `search-score "leche" --source Alcampo` → `No products found or scored.`; README product URL → `Alcampo evidence incomplete: missing ingredients, sugars_g, protein_g, fat_g, saturated_fat_g, salt_g, carbs_g` |
| **Consum** | **No** (0 results) | **No** | No | No | **broken** | Search page is a JS-rendered Angular shell with zero product anchors. The product API's `attributeGroups` contains only `hidden.*`/`filter.*` entries; sampled products expose no ingredient or nutrition groups, and the configured nutritional-info JSON returned 404 for sampled EANs. | `search-score "leche" --source Consum` and `... "yogur" ...` → `No products found or scored.`; README product URL → `Consum evidence incomplete: missing ingredients, sugars_g, protein_g, fat_g, saturated_fat_g, salt_g, carbs_g` |
| **Carrefour España** | No | No | No | No | **broken** (removed) | Removed from the registry: unauthenticated requests return `403 Forbidden` before product data. Requests are rejected by the URL/evidence guardrail. | `search-score "leche" --source Carrefour` → `Provider 'Carrefour' is not a verified provider...`; `score-url "https://www.carrefour.es/..."` → `Product URL hostname is not a supported supermarket.` |
| **El Corte Inglés** | No | No | No | No | **broken** (removed) | Removed from the registry: Akamai returns access denied for simple unauthenticated requests. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Lidl Spain** | No | No | No | No | **broken** (removed) | Removed from the registry: connection terminates before product data can be inspected. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Aldi ES** | No | No | No | No | **broken** (removed) | Removed from the registry: brochure/catalogue site without a persistent product API; known product URL patterns returned 404. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Spar ES** | No | No | No | No | **broken** (removed) | Removed from the registry: reachable site is corporate and has no online store or product evidence path. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Hipercor** | No | No | No | No | **broken** (removed) | Removed from the registry: `403 Forbidden` from the same Akamai protection as El Corte Inglés. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Gadis Online** | No | No | No | No | **broken** (removed) | Removed from the registry: connection timeout/no response from this environment. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Covirán** | No | No | No | No | **broken** (removed) | Removed from the registry: connection timeout/no response from this environment. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Caprabo** | No | No | No | No | **broken** (removed) | Removed from the registry: `403 Forbidden` behind a WAF; no bypass was attempted. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Condis** | No | No | No | No | **broken** (removed) | Removed from the registry: connection timeout/no response from this environment. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Froiz** | No | No | No | No | **broken** (removed) | Removed from the registry: connection timeout/no response from this environment. | Recorded exploration notes; URL allowlist rejects the domain. |
| **Bon Preu / Esclat** | No | No | No | No | **broken** (removed) | Removed from the registry: the partial connector exposed identity/metadata but not ingredients or nutrition. | Recorded exploration notes; URL allowlist rejects the domain. |

\* Open Food Facts is kept because its fetched products satisfy the evidence
contract and its API is the open-data fallback. Its search endpoint is degraded
upstream: results are not query-relevant and the service intermittently returns
`503`. This should be revisited in the removal issue if the upstream behaviour
does not recover.

## Structured live matrix

Each row is `search results / fetched successfully / guardrail-passing scored
products`, with `--max-results 5` and a 15-second fetch timeout.

| Provider | `leche` | `yogur` | Notes |
| --- | --- | --- | --- |
| DIA | 5 / 5 / 5 | 5 / 5 / 5 | Ingredients non-empty; 7–8 nutrition keys; 4-of-6 guardrail passes. |
| Eroski | 5 / 5 / 5 | 5 / 5 / 5 | Ingredients non-empty; 7–8 nutrition keys; 4-of-6 guardrail passes. |
| Open Food Facts | 5 / 5 / 5 | 0 / 0 / 0, then 5 / 5 / 5 on retry | Results are evidence-conforming but unrelated to the query; `503` is intermittent. |
| Mercadona | 5 / 0 / 0 | 5 / 0 / 0 | Fetch fails the guardrail because nutrition is missing. |
| Alcampo | 0 / 0 / 0 | 0 / 0 / 0 | Search blocked by WAF. |
| Consum | 0 / 0 / 0 | 0 / 0 / 0 | Search page has no product anchors; product API lacks evidence. |

## Evidence snippets

### DIA

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source DIA --max-results 5
│ 80 │ strong fit │ DIA │ Leche semidesnatada Dia Láctea pack 6 x 1 L │ Dia Láctea │ 4.98 EUR │ │
│ 80 │ strong fit │ DIA │ Leche entera Dia Láctea pack 6 x 1 L        │ Dia Láctea │ 5.76 EUR │ │
...
Top result: Leche semidesnatada Dia Láctea pack 6 x 1 L
Score: 80/100 (strong fit)

$ PYTHONPATH=src python -m peat_product_scorer search-score "yogur" --source DIA --max-results 5
│ 79 │ reasonable fit │ DIA │ Yogur natural con azúcar de caña Dia Láctea 6 x 125 g │ ...
Score: 79/100 (reasonable fit)

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"
Leche entera Dia Láctea pack 6 x 1 L
Score: 80/100 (strong fit)
```

### Eroski

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source Eroski --max-results 5
│ 78 │ reasonable fit │ Eroski │ 18672295 Leche Entera Del Pais Vasco Eroski Brik 1 Litro │ ...
Score: 78/100 (reasonable fit)

$ PYTHONPATH=src python -m peat_product_scorer search-score "yogur" --source Eroski --max-results 5
│ 76 │ reasonable fit │ Eroski │ 227652 Yogur Natural Danone Pack 8X120 G │ ...
Score: 76/100 (reasonable fit)

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://supermercado.eroski.es/es/productdetail/18672295-leche-entera-del-pais-vasco-eroski-brik-1-litro/"
Leche entera del País Vasco EROSKI, brik 1 litro
Score: 78/100 (reasonable fit)
```

### Open Food Facts

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source "Open Food Facts" --max-results 5
│ 70 │ reasonable fit │ Open Food Facts │ Copos de avena extra suaves │ H. & J. Brüggen KG │ ...
│ 70 │ reasonable fit │ Open Food Facts │ Cacao puro desgrasado en polvo │ CHOCOLATES VALOR ... │ ...
│ 66 │ reasonable fit │ Open Food Facts │ Guacamole │ Hacendado, MERCADONA │ ...
Top result: Copos de avena extra suaves
Score: 70/100 (reasonable fit)

$ PYTHONPATH=src python -m peat_product_scorer search-score "yogur" --source "Open Food Facts" --max-results 5
No products found or scored.        # intermittent upstream 503
# retry returned the same unrelated catalogue page (Copos de avena / Guacamole / ...)

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://world.openfoodfacts.org/product/3017620422003"
Nutella
Score: 42/100 (weak fit)
```

The search payloads fetched successfully and passed the guardrail, but the
product names are not milk or yoghurt. This is recorded as degraded upstream
search rather than silent success.

### Mercadona

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source Mercadona --max-results 5
│ - │ - │ Mercadona │ Leche semidesna… Hacendado │ Leche y bebidas vegetales │ 0.83 EUR │ Mercadona evidence incomplete: missing sugars_g, p... │
...
$ PYTHONPATH=src python -m peat_product_scorer score-url "https://tienda.mercadona.es/product/4040/aceite-girasol-refinado-02o-hacendado-botella"
Mercadona evidence incomplete: missing sugars_g, protein_g, fat_g, saturated_fat_g, salt_g, carbs_g.
```

Direct API check: `GET https://tienda.mercadona.es/api/products/10381` returned
`nutrition_information` with only `allergens` and `ingredients`; the nutrition
values that the adapter expects are no longer present.

### Alcampo

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source Alcampo --max-results 5
No products found or scored.

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://www.compraonline.alcampo.es/products/auchan-leche-entera-de-vaca-6-x-1-l-producto-alcampo/54178"
Alcampo evidence incomplete: missing ingredients, sugars_g, protein_g, fat_g, saturated_fat_g, salt_g, carbs_g.
```

Direct request check: the search and README product URLs returned
`x-amzn-waf-action: challenge` with HTTP 202 for a browser User-Agent, and HTTP
403/302 for other User-Agents. The site is behind an AWS WAF challenge from this
environment.

### Consum

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source Consum --max-results 5
No products found or scored.

$ PYTHONPATH=src python -m peat_product_scorer search-score "yogur" --source Consum --max-results 5
No products found or scored.

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://tienda.consum.es/es/p/aceite-de-girasol-alto-oleico/7299873"
Consum evidence incomplete: missing ingredients, sugars_g, protein_g, fat_g, saturated_fat_g, salt_g, carbs_g.
```

The search page returns a 200 Angular shell with no anchor elements. The
product API response for the README product contains `attributeGroups` with
only `hidden.midiadia` and `filter.id.brand.distributor`; there are no
ingredient or nutrition groups to extract.

### Removed providers fail closed

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source Carrefour --max-results 3
Provider 'Carrefour' is not a verified provider. Removed providers are rejected by the evidence guardrail.
# exit code 1

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://www.carrefour.es/supermercado/el-producto/123"
Product URL hostname is not a supported supermarket.
# exit code 1
```

## Keep / remove decision

This audit does **not** remove adapters itself. It feeds the removal issue #16;
the registry remains unchanged here so the decision and its evidence stay
reviewable together.

| Provider | Classification |
| --- | --- |
| **DIA** | keep |
| **Eroski** | keep |
| **Open Food Facts** | keep (degraded upstream search) |
| **Mercadona** | remove (flagged for issue #16) |
| **Alcampo** | remove (flagged for issue #16) |
| **Consum** | remove (flagged for issue #16) |
| **Carrefour España** | remove (already removed) |
| **El Corte Inglés** | remove (already removed) |
| **Lidl Spain** | remove (already removed) |
| **Aldi ES** | remove (already removed) |
| **Spar ES** | remove (already removed) |
| **Hipercor** | remove (already removed) |
| **Gadis Online** | remove (already removed) |
| **Covirán** | remove (already removed) |
| **Caprabo** | remove (already removed) |
| **Condis** | remove (already removed) |
| **Froiz** | remove (already removed) |
| **Bon Preu / Esclat** | remove (already removed) |

**Keep:** DIA, Eroski, Open Food Facts.

**Remove:** Mercadona, Alcampo, Consum (currently registered but broken) plus
all previously removed providers above. Issue #16 should consume this list.

## Reproduction

The commands above use the project CLI. The repository's unit suite pins the
registry-to-audit mapping so a future adapter cannot be added without a row in
this document.

```bash
PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source <PROVIDER>
PYTHONPATH=src python -m peat_product_scorer search-score "yogur" --source <PROVIDER>
PYTHONPATH=src python -m peat_product_scorer score-url "<README product URL>"
```

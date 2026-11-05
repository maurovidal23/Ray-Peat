# Provider audit — 2026-11-04 (rechecked 2026-11-05)

This document records an end-to-end audit of every supermarket provider named
in issue #15 plus Open Food Facts. The audit ran against the current registered
adapter registry (`src/peat_product_scorer/supermarkets/adapters.py`) using live
network requests from the maintainer checkout on **2026-11-04** and was
rechecked on **2026-11-05**. The results below are evidence from those live
runs, not a restatement of the earlier exploration notes. Where the two runs
differ, both are recorded.

A provider is marked **working** only when a real query returns multiple
products whose fetched page supplies non-empty `ingredients` and at least four
of the six guardrail nutrients. A provider that searches but cannot fetch
scoreable evidence is **broken**. The evidence guardrail was not relaxed for
this audit.

## Status table

| Provider | Search works? | Fetch works? | Ingredients? | Nutrition per 100 g? | Verdict | Failure cause | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **DIA** | **No** (blocked; 0 results) | **No** (HTTP 403) | No | No | **broken** | Akamai bot blocking: on 2026-11-04 the homepage returned HTTP 200 while `/api`, `/search` and `/p/` paths returned HTTP 403 from this environment. The 2026-11-05 recheck returned HTTP 403 for all paths, including the homepage. | `search-score "leche"/"yogur" --source DIA` → `No products found or scored.`; `score-url` README milk URL → `Provider fetch failed (blocked): HTTP 403`; `curl` → `403` for `/`, `/api/...`, `/search?q=leche`, and the `/p/` product URL |
| **Eroski** | Yes (3/3 for `leche`, 3/3 for `yogur` on recheck) | Yes (3/3 fetched) | Yes | Yes (7–8 keys; 4-of-6 guardrail passes) | **working** | — | `search-score "leche" --source Eroski` → 78; `search-score "yogur" --source Eroski` → 73 on 2026-11-05 (76 on 2026-11-04); `score-url` README milk URL → 78/100 |
| **Open Food Facts** | **No**: degraded. 4 of 6 bounded attempts returned no products; the 2 successful attempts returned query-irrelevant catalogue items. | Yes (fetched products pass the guardrail) | Yes | Yes (8–9 keys; guardrail passes) | **broken** (degraded search) | Upstream `/api/v2/search` intermittently returns `503`/empty and ignores query semantics: `leche` and `yogur` both return the same unrelated catalogue page (Copos de avena, Cacao puro, Guacamole). Fetch still works, but search does not reliably return query-relevant scoreable products. | 2026-11-05, 3 attempts per query: `leche` → empty, empty, then scores 70/70/66 for Copos de avena/Cacao puro/Guacamole; `yogur` → empty, same unrelated top three, empty. `score-url` Nutella barcode → 42/100 |
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

\* Open Food Facts' fetched products still satisfy the evidence contract, but
the 2026-11-05 recheck failed the audit's search criterion: results are not
query-relevant and the service intermittently returns `503`. It is therefore
recorded as **broken (degraded search)** rather than working-with-caveats. It is
flagged for removal in issue #16; a future connector can be reconsidered if the
upstream search recovers.

## Structured live matrix

Each row is `search results / fetched successfully / guardrail-passing scored
products`, with `--max-results 5` and a 15-second fetch timeout.

| Provider | `leche` | `yogur` | Notes |
| --- | --- | --- | --- |
| DIA | 0 / 0 / 0 | 0 / 0 / 0 | Search and product URLs blocked with HTTP 403 (Akamai) on 2026-11-04 and 2026-11-05. |
| Eroski | 5 / 5 / 5 (3 / 3 / 3 on recheck) | 5 / 5 / 5 (3 / 3 / 3 on recheck) | Ingredients non-empty; 7–8 nutrition keys; 4-of-6 guardrail passes. |
| Open Food Facts | 0 / 0 / 0 on 2 of 3 attempts; 3 / 3 / 3 on 1 attempt | 0 / 0 / 0 on 2 of 3 attempts; 3 / 3 / 3 on 1 attempt | Successful attempts return the same evidence-conforming but query-irrelevant catalogue items; `503`/empty is intermittent. |
| Mercadona | 5 / 0 / 0 | 5 / 0 / 0 | Fetch fails the guardrail because nutrition is missing. |
| Alcampo | 0 / 0 / 0 | 0 / 0 / 0 | Search blocked by WAF. |
| Consum | 0 / 0 / 0 | 0 / 0 / 0 | Search page has no product anchors; product API lacks evidence. |

## Evidence snippets

### DIA

Live recheck on 2026-11-05 (blocked by Akamai from this environment):

```text
$ PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source DIA --max-results 3
No products found or scored.

$ PYTHONPATH=src python -m peat_product_scorer search-score "yogur" --source DIA --max-results 3
No products found or scored.

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://www.dia.es/huevos-leche-y-mantequilla/leche/p/608P6"
Provider fetch failed (blocked): HTTP 403
# exit code 1

$ for u in / /api/v1/search-back/search?q=leche /search?q=leche \
    /huevos-leche-y-mantequilla/leche/p/608P6; do
    curl -s -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0' "https://www.dia.es$u"; done
403
403
403
403
```

The 2026-11-04 run recorded the same HTTP 403 on `/api`, `/search` and `/p/`
paths, with the homepage returning HTTP 200 at that time. Earlier exploration
output showing scores for DIA is no longer reproducible from this environment
and is not used as the current verdict.

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

Bounded live retries on 2026-11-05 (three attempts per query):

```text
$ for i in 1 2 3; do ... search-score "leche" --source "Open Food Facts" --max-results 3; done
attempt 1: No products found or scored.
attempt 2: No products found or scored.
attempt 3:
│ 70 │ reasonable fit │ Open Food Facts │ Copos de avena extra suaves │ H. & J. Brüggen KG │ ...
│ 70 │ reasonable fit │ Open Food Facts │ Cacao puro desgrasado en polvo │ CHOCOLATES VALOR ... │ ...
│ 66 │ reasonable fit │ Open Food Facts │ Guacamole │ Hacendado, MERCADONA │ ...
Top result: Copos de avena extra suaves
Score: 70/100 (reasonable fit)

$ for i in 1 2 3; do ... search-score "yogur" --source "Open Food Facts" --max-results 3; done
attempt 1: No products found or scored.
attempt 2: same unrelated top three (Copos de avena / Cacao puro / Guacamole)
attempt 3: No products found or scored.

$ PYTHONPATH=src python -m peat_product_scorer score-url "https://world.openfoodfacts.org/product/3017620422003"
Nutella
Score: 42/100 (weak fit)
```

Search succeeds intermittently, and successful payloads pass the guardrail, but
the returned products are not milk or yoghurt. This fails the audit's
query-relevance and reliability criterion, so it is recorded as broken/degraded
search rather than silent success. Fetching a known product URL still works.

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
| **Eroski** | keep |
| **DIA** | remove (flagged for issue #16; blocked by Akamai HTTP 403) |
| **Open Food Facts** | remove (flagged for issue #16; degraded upstream search) |
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

**Keep:** Eroski.

**Remove:** DIA, Open Food Facts, Mercadona, Alcampo, and Consum (currently
registered but broken), plus all previously removed providers above. Issue #16
should consume this list.

## Reproduction

The commands above use the project CLI. The repository's unit suite pins the
registry-to-audit mapping so a future adapter cannot be added without a row in
this document.

```bash
PYTHONPATH=src python -m peat_product_scorer search-score "leche" --source <PROVIDER>
PYTHONPATH=src python -m peat_product_scorer search-score "yogur" --source <PROVIDER>
PYTHONPATH=src python -m peat_product_scorer score-url "<README product URL>"
```

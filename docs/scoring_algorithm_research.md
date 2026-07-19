# Product Scoring Algorithm Research

Research date: 2026-07-01

This document summarizes established food scoring systems that are relevant to
`ray-peat-product-scorer`, compares their algorithms, and proposes a practical
scoring architecture for this project.

This is product-ranking research, not medical advice. The project's Ray
Peat-inspired score should remain framed as an explainable heuristic and should
not be presented as a validated health claim.

## Executive Summary

The strongest model to study is Nutri-Score because it is transparent,
government-backed in several European countries, calculated per 100 g or 100 mL,
and designed for front-of-pack product comparison. The 2023 updated Nutri-Score
algorithm uses negative points for energy, saturated fat, sugars, salt, and
non-nutritive sweeteners in beverages, then subtracts positive points for fibre,
protein, and fruits, vegetables, and legumes. It uses separate logic for general
foods, cheeses, red meat, fats/oils/nuts/seeds, and beverages.

For this project, a direct Nutri-Score clone would not be enough. Nutri-Score
does not account for additives, seed oils, calcium/phosphorus balance, fortified
iron, gums, processing level, or whether carbohydrate comes from fruit/sucrose
versus starch. Those are central to the current Ray Peat-style rule set. A better
approach is a layered algorithm:

1. `nutrition_profile`: a Nutri-Score-like nutrient balance module.
2. `ingredient_profile`: ingredient penalties and bonuses from the current
   knowledge base.
3. `processing_profile`: NOVA-like processing and additive signals.
4. `context_profile`: category-specific exceptions and evidence quality.
5. `final_score`: weighted, explainable aggregation with confidence.

The recommended final output should keep the existing 0-100 score, but add
component subscores, evidence coverage, and category-aware explanations. This
will make the score easier to debug, compare, and tune.

## Goals For This Project

The scorer should:

- Compare supermarket products consistently when labels provide incomplete data.
- Explain every major score movement in user-readable language.
- Penalize the ingredients this framework cares about even when standard nutrient
  profiles would miss them.
- Avoid pretending to be a clinical nutrition model.
- Support category-specific scoring so milk, cheese, oils, sweets, and prepared
  meals are not judged by one flat rule set.
- Preserve the current simple API shape while allowing a richer scoring engine
  internally.

## Established Scoring Systems

### Nutri-Score

Nutri-Score is a front-of-pack label using five classes from A to E. Sante
publique France describes it as a simplified complement to mandatory nutrition
declarations. It was first implemented in France in 2017 and is recommended by
France, Belgium, Switzerland, Germany, Spain, the Netherlands, and Luxembourg.

The updated algorithm was proposed by the European Scientific Committee in 2023
and is being phased in by country. It came into force in Germany, Belgium,
Switzerland, and the Netherlands on 2024-01-01; Luxembourg on 2024-03-05; and
France on 2025-03-16.

Core algorithm:

- Calculate per 100 g or 100 mL.
- Add a negative component `N`.
- Add a positive component `P`.
- Final nutritional score is normally `N - P`.
- Lower nutritional score maps to a better A-E class.

General updated negative components:

- Energy.
- Saturated fatty acids.
- Sugars.
- Salt.

General updated positive components:

- Protein.
- Fibre.
- Fruits, vegetables, and legumes.

Important special cases:

- Cheese keeps full protein subtraction even when negative points are high.
- Red meat and red meat products cap protein points at 2.
- Fats, oils, nuts, and seeds use special fat-quality logic, including energy
  from saturates and saturates/lipids ratio.
- Beverages use separate tables and include a penalty for non-nutritive
  sweeteners.
- Water is treated specially; milk and milk-based beverages are beverages in the
  updated algorithm.

Strengths:

- Public, transparent, and widely implemented.
- Good for product-to-product comparison within similar categories.
- Uses label data that supermarkets usually expose.
- Category-specific logic improves fairness.

Limitations for this project:

- No direct additive, gum, carrageenan, phosphate, fortified iron, or seed-oil
  quality handling except indirectly through nutrients.
- No calcium/phosphorus ratio.
- No distinction between Ray Peat-favored sugars and starches.
- No explicit processing score.
- A product can score well nutritionally while containing ingredients this
  project wants to flag.

### UK Nutrient Profiling Model

The UK Nutrient Profiling Model was developed by the Food Standards Agency for
Ofcom to identify foods and drinks high in saturated fat, sugar, or salt for
advertising restrictions. The current policy model is NPM 2004/2005, while NPM
2018 was published in January 2026 for reference and is not yet applied to
policy.

Core idea:

- Score less beneficial nutrients.
- Score beneficial nutrients.
- Combine them into an overall classification.

Strengths:

- Regulatory use case.
- Closely related to the family of models behind Nutri-Score.
- Good reference for thresholding and policy rigor.

Limitations:

- Built for advertising eligibility, not consumer product ranking.
- Less suitable as the user-facing score for this app.

### Health Star Rating

Health Star Rating is an Australia/New Zealand front-of-pack label. It calculates
a 0.5 to 5 star rating from a calculator developed with Food Standards Australia
New Zealand and nutrition experts.

Core inputs:

- Energy.
- Saturated fat.
- Sodium.
- Sugar.
- Fibre.
- Protein.
- Fruit, vegetable, nut, and legume content.

Important design guidance:

- Ratings are calculated per 100 g or 100 mL.
- Products should be compared with similar products, not across unrelated
  supermarket categories.
- The official system explicitly says it does not consider processing methods,
  vitamins, minerals, or other health effects of ingredients.

Strengths:

- Very practical score presentation.
- Strong category-aware comparison guidance.
- Useful model for a consumer-friendly scale.

Limitations:

- Does not capture this project's ingredient philosophy.
- Voluntary label can be selectively displayed by manufacturers.
- Star scores are intuitive but less precise than this project's current 0-100
  scale.

### NOVA

NOVA classifies foods by processing level, not nutrient quality:

1. Unprocessed or minimally processed foods.
2. Processed culinary ingredients.
3. Processed foods.
4. Ultra-processed foods.

Strengths:

- Catches something nutrient models miss: industrial formulation.
- Very relevant for additives, emulsifiers, modified starches, protein isolates,
  sweeteners, flavorings, and other ingredient-list signals.

Limitations:

- It is not a nutrient score.
- Category assignment can be ambiguous from supermarket data.
- It should be used as a secondary dimension, not as the whole score.

### Food Compass

Food Compass is a Tufts nutrient profiling system published in Nature Food in
2021. It scores foods from 1 to 100 across 54 attributes in 9 domains, including
nutrient ratios, vitamins, minerals, food ingredients, additives, processing,
specific lipids, fibre/protein, and phytochemicals.

Strengths:

- Much broader than Nutri-Score.
- Uses a 1-100 scale similar to this project.
- Includes additives and processing domains.

Limitations:

- More data-hungry than supermarket labels usually allow.
- Harder to implement faithfully without a complete nutrient database.
- Less aligned with European front-of-pack conventions than Nutri-Score.

### Green-Score / Eco-Score

Green-Score, formerly Eco-Score, is an environmental score rather than a health
score. It is useful as a design reference for transparent A-E labels, but it
should not be mixed into the nutrition score unless the product explicitly adds a
sustainability dimension.

## Design Lessons

The recurring algorithmic pattern is:

1. Normalize product data per 100 g or 100 mL.
2. Detect product category.
3. Score limiting factors.
4. Score favorable factors.
5. Apply category-specific caps and exceptions.
6. Map raw score to a user-facing band.
7. Explain the factors that moved the score.

The most important lesson is category detection. A single rule for all foods
creates bad edge cases:

- Whole milk versus soda.
- Cheese versus meat.
- Olive oil versus sunflower oil.
- Plain yoghurt versus sweetened dessert yoghurt.
- Juice versus fruit drink with sweeteners.
- Prepared meals versus single-ingredient foods.

## Proposed Algorithm For This Project

Keep the final output as `0-100`, where higher is better, but compute it from
several component scores.

Suggested component weights:

| Component | Weight | Purpose |
| --- | ---: | --- |
| Nutrition profile | 30 | Label-based nutrient balance. |
| Ingredient profile | 35 | Ray Peat-specific ingredient rules. |
| Processing profile | 15 | NOVA-like additive and industrial formulation signals. |
| Mineral/fat quality profile | 15 | Calcium/phosphorus, PUFA/seed oil, saturated fat context. |
| Evidence quality | 5 | Penalize missing critical fields and low parser confidence. |

Formula:

```text
final_score =
  0.30 * nutrition_profile +
  0.35 * ingredient_profile +
  0.15 * processing_profile +
  0.15 * mineral_fat_quality_profile +
  0.05 * evidence_quality
```

Component scores should each be 0-100. Reasons should be attached to components,
not only to the final score.

### Category Detection

Create a `product_category` field before scoring:

- `dairy_milk`
- `dairy_fermented`
- `cheese`
- `fruit_or_juice`
- `sweetened_beverage`
- `water`
- `oil_or_fat`
- `meat_red`
- `meat_poultry`
- `fish_or_seafood`
- `starch_or_cereal`
- `confectionery`
- `prepared_meal`
- `sauce_or_condiment`
- `unknown`

Use evidence in this order:

1. Supermarket category metadata.
2. Open Food Facts category, if added later.
3. Product name and generic name.
4. Ingredient list.
5. Nutrition pattern fallback.

Always expose category confidence.

### Nutrition Profile

Implement a simplified Nutri-Score-like nutrient module, but map it to 0-100.

Negative nutrient points:

- Energy density.
- Sugars, category-adjusted.
- Salt/sodium.
- Saturated fat, category-adjusted.

Positive nutrient points:

- Protein.
- Fibre.
- Fruit/vegetable/legume percentage if known or inferable.
- Calcium for dairy categories.

Ray Peat-specific adjustments:

- Do not penalize sugar equally in all contexts. Sugar in milk, fruit juice,
  honey, or sucrose-based simple foods can be treated less harshly than sugar in
  ultra-processed starch/fat products.
- Penalize high starch when paired with seed oils or phosphate additives.
- Reward dairy calcium/protein when ingredients are simple.

### Ingredient Profile

This should evolve from the current YAML rules. Recommended groups:

Positive:

- Milk, yoghurt, cheese, casein.
- Fruit, fruit juice, honey, sucrose.
- Gelatin/collagen.
- Shellfish and white fish, if the project wants to reflect low-PUFA protein
  preferences.
- Coconut oil, butter, cocoa butter, ruminant fat, if verified in ingredients.

Negative:

- Seed oils: sunflower, soybean, corn, rapeseed/canola, generic vegetable oil.
- Hydrogenated or interesterified oils.
- Soy protein, soy lecithin, soy isolates.
- Carrageenan and gums.
- Phosphate additives.
- Fortified iron.
- Artificial/non-nutritive sweeteners when not aligned with the framework.
- Maltodextrin, modified starches, glucose-fructose syrup, protein isolates as
  processing markers.

The current scorer already handles many of these as simple term matches. The
next step is to group them into typed ingredient signals with severity and
confidence.

### Processing Profile

Use NOVA as a signal framework, not as a strict claim unless the evidence is
strong.

Suggested scoring:

- 90-100: single/minimal ingredient foods.
- 70-89: simple processed foods with recognizable ingredients.
- 40-69: processed foods with several additives or refined components.
- 0-39: ultra-processed pattern with cosmetic additives, isolates, modified
  starches, sweeteners, flavorings, or industrial emulsifiers.

Expose labels such as:

- `processing_low`
- `processing_moderate`
- `processing_high`
- `processing_uncertain`

### Mineral And Fat Quality Profile

This is where the project can differ from mainstream labels.

Signals:

- Calcium/phosphorus ratio.
- Calcium per 100 g or 100 mL in dairy.
- Phosphate additives.
- Fat source quality from ingredient list.
- Saturated fat context: butter/cocoa/coconut/ruminant fat versus generic
  refined vegetable oils.
- Total fat without ingredient context should reduce confidence or add a mild
  penalty.

Potential thresholds:

- Calcium/phosphorus ratio >= 1.0: strong positive.
- Calcium/phosphorus ratio 0.5-1.0: mild positive or neutral.
- Ratio unavailable: no direct penalty, but lower evidence confidence.
- Seed oil present: strong negative even if saturated fat is low.
- Oil/fat category with olive oil or butter: category-specific neutral/positive
  rather than using a generic high-fat penalty.

### Evidence Quality

A score should not look precise when the data is weak.

Suggested fields:

- `evidence_quality_score`: 0-100.
- `missing_fields`: already exists.
- `ingredient_source`: already exists.
- `nutrition_source`: add if practical.
- `category_confidence`: add.
- `warnings`: list of caveats.

Evidence quality should drop when:

- Ingredients are missing.
- Nutrition table is missing.
- Only product name is available.
- Category is inferred from weak text.
- Key nutrients required for a component are absent.

Do not heavily penalize the product itself for missing data. Instead, show lower
confidence and make the comment cautious.

## Proposed Output Shape

Current output:

```json
{
  "score": 72,
  "band": "reasonable fit",
  "comment": "...",
  "reasons": []
}
```

Recommended richer output:

```json
{
  "score": 72,
  "band": "reasonable fit",
  "confidence": 84,
  "category": {
    "id": "dairy_fermented",
    "confidence": 92
  },
  "components": {
    "nutrition_profile": 76,
    "ingredient_profile": 82,
    "processing_profile": 72,
    "mineral_fat_quality_profile": 81,
    "evidence_quality": 84
  },
  "reasons": [
    {
      "component": "ingredient_profile",
      "rule_id": "dairy_positive",
      "delta": 14,
      "detail": "Milk ingredient detected."
    }
  ],
  "warnings": []
}
```

## Banding

Keep the existing bands, but define them as product fit bands rather than health
claims:

| Score | Band | Meaning |
| ---: | --- | --- |
| 80-100 | strong fit | Strong match to this product-selection framework. |
| 65-79 | reasonable fit | Mostly compatible; inspect caveats. |
| 45-64 | mixed | Useful positives and negatives both present. |
| 25-44 | weak fit | More concerns than positives. |
| 0-24 | avoid | Strong mismatch or poor evidence with strong negatives. |

## Implementation Plan

1. Add product category detection.
   - New module: `src/peat_product_scorer/categories.py`.
   - Return `category_id`, `confidence`, and evidence.

2. Refactor rules into component groups.
   - Extend `data/knowledge/ray_peat_rules.yaml` with `component`, `severity`,
     and `requires_category` fields.
   - Keep backward compatibility with existing `delta` rules during migration.

3. Add component score models.
   - Extend `ProductScore` with `confidence`, `category`, `components`, and
     `warnings`.

4. Implement `nutrition_profile`.
   - Start with available nutrients: energy, fat, saturated fat, sugars, salt,
     protein, fibre, calcium, phosphorus.
   - Use category modifiers before finalizing score.

5. Implement `processing_profile`.
   - Use ingredient term groups for additives, sweeteners, isolates, modified
     starches, emulsifiers, flavorings, and ingredient count.

6. Implement `mineral_fat_quality_profile`.
   - Move existing calcium/phosphorus and seed-oil logic here.

7. Update comments.
   - Build comments from the top positive reason, top negative reason, category,
     and confidence.

8. Add tests.
   - Plain milk.
   - Sweetened yoghurt.
   - Sunflower oil cookies.
   - Olive oil.
   - Cola with sugar.
   - Diet soda with non-nutritive sweetener.
   - Cheese with high saturated fat but high calcium/protein.
   - Missing ingredients.

## Candidate Data Model Changes

```python
class ScoreComponent(BaseModel):
    id: str
    score: int
    weight: float
    reasons: list[ScoreReason] = []
    confidence: int = 100


class ProductCategory(BaseModel):
    id: str
    label: str
    confidence: int
    evidence: list[str] = []


class ProductScore(BaseModel):
    score: int
    band: str
    comment: str
    reasons: list[ScoreReason]
    product: Product
    confidence: int = 100
    category: ProductCategory | None = None
    components: list[ScoreComponent] = []
    warnings: list[str] = []
```

## Practical First Version

The first robust version does not need to fully implement official Nutri-Score.
It should borrow the architecture:

- Category first.
- Negative nutrient profile.
- Positive nutrient profile.
- Ingredient and processing modules.
- Transparent component explanations.

The main scoring behavior should remain Ray Peat-specific, not mainstream
Nutri-Score-specific. Nutri-Score should be treated as a benchmark and design
pattern, not as the product's identity.

## Source Notes

- Sante publique France, Nutri-Score overview and files:
  https://www.santepubliquefrance.fr/en/nutri-score
- Sante publique France, Nutri-Score Q&A, English version dated 2025-03-17:
  https://www.santepubliquefrance.fr/sites/default/files/rdd/document/FAQ-updatedAlgo-V11.pdf
- Sante publique France, 2022 Scientific Committee report on solid foods:
  https://www.santepubliquefrance.fr/sites/default/files/rdd/document/2022-main%20algorithm%20report%20update_FINAL.pdf
- Sante publique France, 2023 beverage update report:
  https://www.santepubliquefrance.fr/nutrition-et-activite-physique/rapportsynthese/update-nutri-score-algorithm-beverages-second-update-report-scientific-committee-nutri-score-v2-2023
- UK Department of Health and Social Care, Nutrient Profiling Model 2004/2005:
  https://www.gov.uk/government/publications/the-nutrient-profiling-model
- UK Department of Health and Social Care, Nutrient Profiling Model 2018:
  https://www.gov.uk/government/publications/nutrient-profiling-model-2018
- Health Star Rating, how ratings are calculated:
  https://www.healthstarrating.gov.au/about/how-ratings-are-calculated
- Health Star Rating, calculator and implementation guide:
  https://www.healthstarrating.gov.au/
- Mozaffarian et al., Food Compass, Nature Food, 2021:
  https://www.nature.com/articles/s43016-021-00381-y
- Tufts Food Compass project:
  https://tuftsfoodismedicine.org/food-compass/
- Open Food Facts Green-Score:
  https://world.openfoodfacts.org/green-score


## Evolution From The Current Scorer

This section connects the research above to the current implementation in `src/peat_product_scorer/scorer.py`. The goal is not to clone Nutri-Score. The goal is to borrow its architecture: category detection, separate negative and positive dimensions, transparent component scoring, and clear banding. The principles, however, should come from the Ray Peat-inspired framework already encoded in the project.

### Current Scorer Baseline

The current scorer is a flat rule engine:

1. `score_product()` loads `data/knowledge/ray_peat_rules.yaml`.
2. Every product starts from `base_score: 50`.
3. Evidence is built from product name, description, and ingredients.
4. Text is normalized with accent-insensitive lowercase matching.
5. A rule can trigger from ingredient/name terms, a nutrient threshold, or a nutrient ratio.
6. The rule's `delta` is added directly to the global score.
7. The final score is clamped to `0-100`.
8. `_score_band()` maps it to `strong fit`, `reasonable fit`, `mixed`, `weak fit`, or `avoid`.
9. `_build_comment()` writes a short comment from the first positive and/or negative reason.

The current implementation is useful because it is explainable and easy to tune, but it mixes several concepts into one list of deltas: ingredients, nutrients, processing, mineral balance, fat quality, protein quality, and evidence quality. The next version should preserve the same intent while separating those concepts.

### Existing Rule Intent

Current positive signals:

| Rule | Meaning |
| --- | --- |
| `dairy_positive` | Milk, cheese, yoghurt, cream, or casein is favorable. |
| `fruit_sugar_positive` | Fruit, juice, honey, sugar, or sucrose is favorable. |
| `gelatin_collagen_positive` | Gelatin/collagen is favorable. |
| `high_sugar_positive` | Sugar >= 8 g/100 g can be favorable in context. |
| `high_protein_positive` | Protein >= 8 g/100 g is favorable, but currently without source control. |
| `calcium_phosphorus_positive` | Calcium/phosphorus ratio >= 1.0 is favorable. |

Current negative signals:

| Rule | Meaning |
| --- | --- |
| `seed_oils_negative` | Sunflower, soy, rapeseed/canola, corn, or generic vegetable oils are strongly penalized. |
| `soy_negative` | Soy ingredients are penalized. |
| `gums_negative` | Carrageenan and common gums are penalized. |
| `phosphate_additives_negative` | Phosphate additives are penalized. |
| `fortified_iron_negative` | Added iron is penalized. |
| `high_fat_without_context_negative` | High total fat is mildly penalized when source context is missing. |

The batch results in `data/research/ray_peat_comprehensive_results.json` show the intended ranking shape: dairy desserts, yoghurts, milk-based products, cheeses, and gelatin/collagen products rise when strong negatives are absent; sunflower oil, margarines, pizzas, seed-oil prepared foods, soy/gum/phosphate products, and fortified formulas fall. The new architecture should preserve that broad ranking while fixing weak evidence and category edge cases.

## Ray Peat-Derived Principles For The New Architecture

These principles are scoring assumptions, not medical claims. They should remain configurable in the knowledge base and visible in explanations.

### 1. Context Comes Before Isolated Nutrients

Nutri-Score starts from universal quantities such as energy, sugar, saturated fat, salt, fibre, protein, and fruit/vegetable content. This project should start from context:

- What category is the product?
- Which ingredients provide the macros?
- Is sugar coming with dairy or fruit, or with refined starch and seed oil?
- Is fat coming from butter/cocoa/coconut/ruminant fat, olive oil, or seed oil?
- Is protein coming from dairy/collagen/shellfish, or from soy/protein isolates?

The scorer should not have one universal opinion about `sugar`, `fat`, or `protein`. Source changes meaning.

### 2. PUFA Avoidance Is A Primary Negative Signal

The current `seed_oils_negative` rule should become a first-class fat-quality principle. Sunflower, soybean, corn, rapeseed/canola, and generic vegetable oils are not mild issues in this framework; they are core avoid signals.

Algorithm consequences:

- Seed oil strongly reduces `fat_quality_profile`.
- Seed oil also reduces `processing_profile` when it appears in prepared industrial foods.
- High total fat should not be penalized by itself until fat source is known.
- Butter, cocoa butter, coconut oil, dairy fat, olive oil, and ruminant fat need separate treatment from seed oils.

### 3. Dairy Is A Reference Positive Category

Dairy should be a first-class category, not just a term match. In this framework, simple dairy can be favorable because it can provide calcium, protein, sugar, and a better calcium/phosphorus balance than many muscle-meat-heavy foods.

Algorithm consequences:

- Detect `dairy_milk`, `dairy_fermented`, `cheese`, `cream`, and `dairy_dessert` separately.
- Reward simple dairy ingredient lists more than long industrial dairy desserts.
- Reward calcium and calcium/phosphorus balance when measured.
- Do not let gums, carrageenan, seed oils, starches, phosphates, or fortified iron disappear behind a dairy-positive label.

### 4. Sugar Source Should Be Interpreted

Mainstream nutrient scores often treat sugar as a universal negative. The current rules treat fruit, juice, honey, sucrose, and sugar more favorably. The evolved scorer should preserve that difference while adding guardrails.

Algorithm consequences:

- Interpret `sugars_g` by category and ingredient source.
- Fruit, juice, honey, sucrose, lactose, and simple dairy desserts can be neutral or positive when strong negatives are absent.
- Sugar combined with seed oils, refined starches, gums, and flavoring systems should not get the same positive treatment.
- Non-nutritive sweeteners should be a separate negative or caution signal, not silently treated as low sugar.

### 5. Starch And Industrial Additives Are Caution Signals

The Ray Peat article library in this repository includes repeated concern around starch, persorption, gums, carrageenan, and gut irritation. The scorer should not turn that into clinical claims, but it can encode this product-selection preference:

- refined starch-heavy products are less preferred than fruit/sugar/dairy carbohydrate sources;
- gums and carrageenan are additive negatives;
- modified starches, maltodextrin, flavoring systems, emulsifiers, and long industrial ingredient lists reduce processing quality.

Algorithm consequences:

- Include starch and additive signals in `processing_profile`.
- Penalize starch more when paired with seed oils, phosphates, gums, or soy.
- Treat traditional/simple starch foods differently from ultra-processed starch-fat snacks.

### 6. Mineral Balance Matters

Nutri-Score does not directly care about calcium/phosphorus balance. This project should. The current `calcium_phosphorus_positive` rule is a good seed but should be expanded.

Algorithm consequences:

- Reward calcium/phosphorus ratio >= 1.0 when both values are known.
- Reward calcium density in dairy categories.
- Penalize phosphate additives even when phosphorus is not listed in nutrition.
- Treat missing calcium/phosphorus as an evidence gap, not an automatic product penalty.

### 7. Protein Quality Is Source-Dependent

Protein grams alone should not drive a high score. The current `high_protein_positive` rule is useful but too broad.

Algorithm consequences:

- Dairy protein, gelatin/collagen, shellfish, white fish, and eggs can be positive depending on final philosophy.
- Soy protein, pea protein isolates, generic protein isolates, and heavily fortified high-protein products should be scored cautiously.
- Red meat should not be treated the same as dairy protein because the mineral and phosphorus context differs.

### 8. Additives Are Central, Not Secondary

Gums, carrageenan, phosphates, fortified iron, sweeteners, colors, flavorings, and emulsifiers should be visible in output. They are not always captured by macros, but they are central to this product-selection lens.

Algorithm consequences:

- Additive signals live in both `ingredient_profile` and `processing_profile`.
- Reasons list the exact detected additives.
- A product can have a decent nutrient profile but still have a weak final score if additive burden is high.

### 9. Confidence Is Separate From Compatibility

A product with missing ingredients is not necessarily bad; it is uncertain. The current scorer can make strong claims from name and nutrition evidence alone. The evolved scorer should separate:

- `score`: compatibility with the Ray Peat-inspired framework;
- `confidence`: completeness and reliability of evidence.

Algorithm consequences:

- Missing ingredients strongly lowers confidence.
- Missing nutrition lowers confidence depending on category.
- Product-name matches have lower evidence weight than parsed ingredient matches.
- Comments say when the score is based on limited evidence.

## Architecture Differences From Nutri-Score

The project should borrow Nutri-Score's discipline, not its value system.

| Area | Nutri-Score-like model | Ray Peat-inspired model |
| --- | --- | --- |
| Primary unit | Nutrient profile per 100 g/ml | Ingredient-context profile with nutrient support |
| Sugar | Usually negative above thresholds | Contextual: fruit, sucrose, honey, and lactose may be favorable |
| Saturated fat | Usually negative, with exceptions | Source-dependent; dairy/cocoa/coconut/ruminant context matters |
| PUFA/seed oils | Mostly indirect | Direct major negative |
| Protein | Usually positive, with caps | Positive only when source quality is compatible |
| Fibre | Usually positive | Not automatically positive; source and gut context matter |
| Dairy | Category exception | Core reference-positive category when simple |
| Additives | Mostly ignored | Central ingredient and processing signals |
| Processing | Mostly ignored | Explicit NOVA-like profile |
| Minerals | Limited | Calcium, phosphorus, phosphate additives, and iron fortification matter |
| Output | A-E public-health label | 0-100 compatibility score with reasons and confidence |

The final scorer should explain intentional disagreements with Nutri-Score. A sugary plain dairy product may score better here than in Nutri-Score. A low-sugar product with seed oil, gums, and sweeteners may score worse. A high-fat oil is not judged by fat quantity alone: olive oil, butter, coconut oil, and sunflower oil require different fat-quality treatment.

## Incremental Implementation Path

### Phase 1: Add Metadata To Existing Rules

Extend each YAML rule with type information while keeping `delta` for backward compatibility:

```yaml
- id: seed_oils_negative
  component: fat_quality_profile
  principle: pufa_avoidance
  evidence_type: ingredient
  severity: major
  direction: negative
  delta: -24
```

Target components:

- `ingredient_profile`
- `nutrition_profile`
- `processing_profile`
- `mineral_balance_profile`
- `fat_quality_profile`
- `protein_quality_profile`
- `carbohydrate_context_profile`
- `evidence_quality`

### Phase 2: Add Category Detection Before Rule Evaluation

Create `src/peat_product_scorer/categories.py` and classify the product before scoring. Return category ID, confidence, and evidence.

Example:

```text
detect_category(product) ->
  id: "dairy_fermented"
  confidence: 85
  evidence: ["ingredient: leche", "name: yogur"]
```

Rules can then declare category behavior:

```yaml
applies_to: ["dairy_milk", "dairy_fermented", "dairy_dessert"]
excluded_from: ["sweetened_beverage"]
category_multiplier:
  dairy_fermented: 1.0
  dairy_dessert: 0.7
```

### Phase 3: Add Confidence

Calculate confidence from ingredient presence, nutrition presence, category confidence, source reliability, and evidence type.

Example outputs:

- Full ingredients and nutrition: score 78, confidence 92.
- Nutrition but no ingredients: score 65, confidence 48.
- Only product name: score 55, confidence 20.

### Phase 4: Compute Component Scores

Move from direct global deltas to component scores:

```text
ingredient_profile:
  starts at 70
  + dairy/simple sugar/gelatin positives
  - soy/gums/phosphates/fortified iron negatives

fat_quality_profile:
  starts at 60
  + butter/cocoa/coconut/ruminant/olive signals
  - seed oils/generic vegetable oils/hydrogenated oils

mineral_balance_profile:
  starts at 50
  + calcium density and calcium/phosphorus ratio
  - phosphate additives and high phosphorus without calcium context
```

Then aggregate components by weights into the final `0-100` score.

### Phase 5: Add Principle Tags To Reasons

Reasons should explain what matched and which principle it belongs to:

```json
{
  "rule_id": "seed_oils_negative",
  "component": "fat_quality_profile",
  "principle": "pufa_avoidance",
  "evidence_type": "ingredient",
  "matched_terms": ["aceite de girasol"],
  "delta": -24,
  "detail": "Sunflower oil is a major negative in this framework because the scorer prioritizes low-PUFA fat sources."
}
```

### Phase 6: Improve The Comment

The evolved comment should summarize category, confidence, strongest positive, strongest concern, and missing evidence.

Example:

```text
This looks like a dairy dessert with high evidence confidence. It fits the framework because it contains milk/sugar and no seed-oil signal, but the score is limited by gums and a long additive list.
```

### Phase 7: Calibrate Against Existing Results

Use `data/research/ray_peat_comprehensive_results.json` as a regression and calibration set. Preserve the intended ranking while improving edge cases:

- avoid over-rewarding a product that merely contains the word `leche`;
- avoid giving `azucar` a positive score inside seed-oil, starch-heavy, ultra-processed products;
- avoid penalizing all high-fat products when the fat source is known and compatible;
- make missing ingredients lower confidence instead of silently relying on the product name.


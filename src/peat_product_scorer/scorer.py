from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .categories import detect_category
from .knowledge_base import load_knowledge_base
from .models import (
    Product,
    ProductScore,
    ProviderOutcome,
    ScoreComponent,
    ScoreContribution,
    ScoredSearchResult,
    ScoredSearchResults,
    ScoreReason,
    SearchResult,
)
from .nutrition import normalize_text
from .supermarkets import fetch_product, search_products
from .supermarkets.contract import require_evidence

NUTRITION_BASE_SCORE = 60
NUTRITION_MISSING_BASE_SCORE = 50
INGREDIENT_BASE_SCORE = 62
PROCESSING_MISSING_BASE_SCORE = 45
MINERAL_FAT_BASE_SCORE = 58
EVIDENCE_BASE_SCORE = 100

COMPONENT_WEIGHTS = {
    "nutrition_profile": 0.30,
    "ingredient_profile": 0.35,
    "processing_profile": 0.15,
    "mineral_fat_quality_profile": 0.15,
    "evidence_quality": 0.05,
}


@dataclass
class _ComponentBreakdown:
    base: int
    contributions: list[ScoreContribution] = field(default_factory=list)


def _format_amount(value: float) -> str:
    return f"{value:g}"


def _apply_contribution(
    score: int,
    breakdown: _ComponentBreakdown | None,
    label: str,
    delta: int,
    detail: str,
    rule_id: str | None = None,
) -> int:
    if breakdown is not None and delta != 0:
        breakdown.contributions.append(
            ScoreContribution(
                label=label,
                delta=delta,
                detail=detail,
                rule_id=rule_id,
            )
        )
    return score + delta


def _contains_any(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if normalize_text(term) in text]


def score_product(product: Product) -> ProductScore:
    knowledge = load_knowledge_base()
    rules = knowledge["rules"]
    evidence_text = " ".join(
        part
        for part in [product.name, product.description or "", ", ".join(product.ingredients)]
        if part
    )
    ingredients_text = normalize_text(evidence_text)
    nutrition = product.nutrition_per_100g
    category = detect_category(product)
    reasons: list[ScoreReason] = []

    for rule in rules:
        rule_id = rule["id"]
        delta = int(rule["delta"])
        terms = rule.get("terms", [])
        matched = _contains_any(ingredients_text, terms) if terms else []
        triggered = bool(matched)

        nutrient = rule.get("nutrient")
        if nutrient:
            value = nutrition.get(nutrient)
            minimum = rule.get("min")
            maximum = rule.get("max")
            triggered = value is not None
            if minimum is not None:
                triggered = triggered and value >= float(minimum)
            if maximum is not None:
                triggered = triggered and value <= float(maximum)

        ratio = rule.get("ratio")
        if ratio:
            numerator = nutrition.get(ratio["numerator"])
            denominator = nutrition.get(ratio["denominator"])
            triggered = bool(numerator is not None and denominator and denominator > 0)
            if triggered:
                value = numerator / denominator
                if "min" in ratio:
                    triggered = value >= float(ratio["min"])
                if "max" in ratio:
                    triggered = triggered and value <= float(ratio["max"])

        if not triggered:
            continue

        detail = rule["detail"]
        if matched:
            detail = f"{detail} Detected: {', '.join(matched)}."
        reasons.append(
            ScoreReason(
                rule_id=rule_id,
                label=rule["label"],
                delta=delta,
                detail=detail,
                component=_component_for_rule(rule_id),
                principle=_principle_for_rule(rule_id),
                evidence_type="nutrient" if nutrient or ratio else "ingredient",
                matched_terms=matched,
            )
        )

    components = _build_components(product, category.id, reasons)
    score = _clamp_score(sum(component.score * component.weight for component in components))
    score_adjustments: list[ScoreContribution] = []
    score = _apply_framework_caps(score, category.id, reasons, score_adjustments)
    confidence = _component_by_id(components, "evidence_quality").score
    warnings = _build_warnings(product, category.confidence)
    band = _score_band(score)
    comment = _build_comment(product, score, band, reasons, category.label, confidence, warnings)
    return ProductScore(
        score=score,
        band=band,
        comment=comment,
        reasons=reasons,
        product=product,
        confidence=confidence,
        category=category,
        components=components,
        score_adjustments=score_adjustments,
        warnings=warnings,
    )


def _build_components(product: Product, category_id: str, reasons: list[ScoreReason]) -> list[ScoreComponent]:
    nutrition = product.nutrition_per_100g
    text = normalize_text(" ".join([product.name, product.description or "", " ".join(product.ingredients)]))
    ingredient_reasons = [r for r in reasons if r.component == "ingredient_profile"]
    nutrition_reasons = [r for r in reasons if r.component == "nutrition_profile"]
    fat_mineral_reasons = [r for r in reasons if r.component == "mineral_fat_quality_profile"]

    nutrition_breakdown = _ComponentBreakdown(base=NUTRITION_BASE_SCORE)
    ingredient_breakdown = _ComponentBreakdown(base=INGREDIENT_BASE_SCORE)
    processing_breakdown = _ComponentBreakdown(base=PROCESSING_MISSING_BASE_SCORE)
    mineral_fat_breakdown = _ComponentBreakdown(base=MINERAL_FAT_BASE_SCORE)
    evidence_breakdown = _ComponentBreakdown(base=EVIDENCE_BASE_SCORE)

    processing_score, processing_reasons = _processing_profile_score(
        product, text, processing_breakdown
    )
    components = [
        ScoreComponent(
            id="nutrition_profile",
            label="Nutrition profile",
            score=_nutrition_profile_score(nutrition, category_id, nutrition_breakdown),
            base_score=nutrition_breakdown.base,
            weight=COMPONENT_WEIGHTS["nutrition_profile"],
            reasons=nutrition_reasons,
            contributions=nutrition_breakdown.contributions,
            confidence=80 if nutrition else 25,
        ),
        ScoreComponent(
            id="ingredient_profile",
            label="Ingredient profile",
            score=_ingredient_profile_score(category_id, ingredient_reasons, ingredient_breakdown),
            base_score=ingredient_breakdown.base,
            weight=COMPONENT_WEIGHTS["ingredient_profile"],
            reasons=ingredient_reasons,
            contributions=ingredient_breakdown.contributions,
            confidence=90 if product.ingredients else 30,
        ),
        ScoreComponent(
            id="processing_profile",
            label="Processing profile",
            score=processing_score,
            base_score=processing_breakdown.base,
            weight=COMPONENT_WEIGHTS["processing_profile"],
            reasons=processing_reasons,
            contributions=processing_breakdown.contributions,
            confidence=85 if product.ingredients else 25,
        ),
        ScoreComponent(
            id="mineral_fat_quality_profile",
            label="Mineral and fat quality",
            score=_mineral_fat_quality_score(
                nutrition, text, category_id, fat_mineral_reasons, mineral_fat_breakdown
            ),
            base_score=mineral_fat_breakdown.base,
            weight=COMPONENT_WEIGHTS["mineral_fat_quality_profile"],
            reasons=fat_mineral_reasons,
            contributions=mineral_fat_breakdown.contributions,
            confidence=75 if product.ingredients or nutrition else 25,
        ),
        ScoreComponent(
            id="evidence_quality",
            label="Evidence quality",
            score=_evidence_quality_score(product, evidence_breakdown),
            base_score=evidence_breakdown.base,
            weight=COMPONENT_WEIGHTS["evidence_quality"],
            reasons=[],
            contributions=evidence_breakdown.contributions,
            confidence=100,
        ),
    ]
    return components


def _nutrition_profile_score(
    nutrition: dict[str, float],
    category_id: str,
    breakdown: _ComponentBreakdown | None = None,
) -> int:
    if not nutrition:
        if breakdown is not None:
            breakdown.base = NUTRITION_MISSING_BASE_SCORE
        return NUTRITION_MISSING_BASE_SCORE

    score = NUTRITION_BASE_SCORE
    sugars = nutrition.get("sugars_g")
    protein = nutrition.get("protein_g")
    saturated_fat = nutrition.get("saturated_fat_g")
    salt = nutrition.get("salt_g")
    fiber = nutrition.get("fiber_g")
    calcium = nutrition.get("calcium_mg")

    if sugars is not None:
        if category_id in {"dairy_milk", "dairy_fermented", "dairy_dessert", "fruit_or_juice"}:
            if sugars >= 4:
                score = _apply_contribution(
                    score,
                    breakdown,
                    "Favorable dairy or fruit sugar level",
                    6,
                    f"Sugars {_format_amount(sugars)} g/100 g meet the 4 g dairy/fruit minimum (+6).",
                    "sugar_dairy_positive",
                )
            if sugars > 22:
                score = _apply_contribution(
                    score,
                    breakdown,
                    "Excess dairy or fruit sugar",
                    -8,
                    f"Sugars {_format_amount(sugars)} g/100 g exceed the 22 g dairy/fruit limit (-8).",
                    "sugar_dairy_high_negative",
                )
        else:
            if sugars > 12:
                score = _apply_contribution(
                    score,
                    breakdown,
                    "High sugar content",
                    -8,
                    f"Sugars {_format_amount(sugars)} g/100 g exceed the 12 g general limit (-8).",
                    "sugar_high_negative",
                )
            if sugars > 25:
                score = _apply_contribution(
                    score,
                    breakdown,
                    "Very high sugar content",
                    -8,
                    f"Sugars {_format_amount(sugars)} g/100 g exceed the 25 g upper limit (-8).",
                    "sugar_very_high_negative",
                )
    if protein is not None:
        if protein >= 8:
            score = _apply_contribution(
                score,
                breakdown,
                "High protein content",
                8,
                f"Protein {_format_amount(protein)} g/100 g meets the 8 g high-protein threshold (+8).",
                "protein_high_positive",
            )
        elif protein >= 3:
            score = _apply_contribution(
                score,
                breakdown,
                "Meaningful protein content",
                4,
                f"Protein {_format_amount(protein)} g/100 g meets the 3 g protein threshold (+4).",
                "protein_positive",
            )
    if fiber is not None and fiber >= 3:
        score = _apply_contribution(
            score,
            breakdown,
            "Beneficial fiber content",
            3,
            f"Fiber {_format_amount(fiber)} g/100 g meets the 3 g beneficial-fiber threshold (+3).",
            "fiber_positive",
        )
    if (
        saturated_fat is not None
        and saturated_fat > 5
        and category_id not in {"cheese", "dairy_milk", "oil_or_fat"}
    ):
        score = _apply_contribution(
            score,
            breakdown,
            "High saturated fat",
            -8,
            f"Saturated fat {_format_amount(saturated_fat)} g/100 g exceeds the 5 g limit for category {category_id} (-8).",
            "saturated_fat_high_negative",
        )
    if salt is not None:
        if salt > 1.5:
            score = _apply_contribution(
                score,
                breakdown,
                "High salt content",
                -10,
                f"Salt {_format_amount(salt)} g/100 g exceeds the 1.5 g high-salt threshold (-10).",
                "salt_high_negative",
            )
        elif salt > 0.8:
            score = _apply_contribution(
                score,
                breakdown,
                "Moderate salt content",
                -4,
                f"Salt {_format_amount(salt)} g/100 g exceeds the 0.8 g salt threshold (-4).",
                "salt_moderate_negative",
            )
    if calcium is not None and calcium >= 100 and category_id.startswith("dairy"):
        score = _apply_contribution(
            score,
            breakdown,
            "Favorable dairy calcium",
            8,
            f"Calcium {_format_amount(calcium)} mg/100 g meets the 100 mg dairy calcium threshold (+8).",
            "calcium_dairy_positive",
        )

    return _clamp_score(score)


def _ingredient_profile_score(
    category_id: str,
    reasons: list[ScoreReason],
    breakdown: _ComponentBreakdown | None = None,
) -> int:
    score = INGREDIENT_BASE_SCORE
    if category_id in {"dairy_milk", "dairy_fermented", "cheese"}:
        score = _apply_contribution(
            score,
            breakdown,
            "Dairy category bonus",
            8,
            f"Category {category_id} adds the 8 point dairy ingredient bonus (+8).",
            "dairy_category_bonus",
        )
    if category_id == "fruit_or_juice":
        score = _apply_contribution(
            score,
            breakdown,
            "Fruit category bonus",
            6,
            f"Category {category_id} adds the 6 point fruit ingredient bonus (+6).",
            "fruit_category_bonus",
        )
    has_major_negative = _has_major_negative(reasons)
    for reason in reasons:
        multiplier = (
            0.65
            if reason.rule_id == "fruit_sugar_positive" and has_major_negative
            else 1.0
        )
        applied = round(reason.delta * multiplier)
        if applied == 0:
            continue
        matched = f" Matched: {', '.join(reason.matched_terms)}." if reason.matched_terms else ""
        if multiplier != 1.0:
            detail = (
                f"{reason.label} rule delta {reason.delta:+d} scaled by {multiplier:g} "
                f"because a major negative is present = {reason.delta * multiplier:g}, "
                f"rounded to {applied:+d}.{matched}"
            )
        else:
            detail = f"{reason.label} rule delta {reason.delta:+d} applied directly.{matched}"
        score = _apply_contribution(
            score,
            breakdown,
            reason.label,
            applied,
            detail,
            reason.rule_id,
        )
    return _clamp_score(score)


def _processing_profile_score(
    product: Product,
    text: str,
    breakdown: _ComponentBreakdown | None = None,
) -> tuple[int, list[ScoreReason]]:
    if not product.ingredients:
        if breakdown is not None:
            breakdown.base = PROCESSING_MISSING_BASE_SCORE
        return PROCESSING_MISSING_BASE_SCORE, []

    ingredient_count = len(product.ingredients)
    score = 92 if ingredient_count <= 2 else 78 if ingredient_count <= 6 else 60
    if breakdown is not None:
        breakdown.base = score
    reasons: list[ScoreReason] = []
    markers = {
        "modified_starch": ("Modified starch or maltodextrin", -14, ["almidon modificado", "maltodextrina"]),
        "sweeteners": ("Non-nutritive sweetener", -14, ["aspartamo", "sucralosa", "acesulfamo", "sacarina", "ciclamato"]),
        "flavorings": ("Flavoring system", -8, ["aroma", "aromas"]),
        "emulsifiers": ("Industrial emulsifier", -8, ["emulgente", "mono y digliceridos", "e471"]),
        "protein_isolates": ("Protein isolate", -10, ["proteina aislada", "aislado de proteina", "proteina de guisante"]),
    }
    for rule_id, (label, delta, terms) in markers.items():
        matched = _contains_any(text, terms)
        if not matched:
            continue
        score = _apply_contribution(
            score,
            breakdown,
            label,
            delta,
            f"{label} marker matched '{', '.join(matched)}' at ingredient count {ingredient_count} ({delta:+d}).",
            rule_id,
        )
        reasons.append(
            ScoreReason(
                rule_id=rule_id,
                label=label,
                delta=delta,
                detail=f"Processing marker detected: {', '.join(matched)}.",
                component="processing_profile",
                principle="processing_burden",
                evidence_type="ingredient",
                matched_terms=matched,
            )
        )
    if ingredient_count > 10:
        score = _apply_contribution(
            score,
            breakdown,
            "Long ingredient list",
            -10,
            f"Ingredient list has {ingredient_count} ingredients, above the 10 ingredient limit (-10).",
            "long_ingredient_list",
        )
        reasons.append(
            ScoreReason(
                rule_id="long_ingredient_list",
                label="Long ingredient list",
                delta=-10,
                detail="A long ingredient list lowers the processing profile confidence and fit.",
                component="processing_profile",
                principle="processing_burden",
                evidence_type="ingredient",
            )
        )
    return _clamp_score(score), reasons


def _mineral_fat_quality_score(
    nutrition: dict[str, float],
    text: str,
    category_id: str,
    reasons: list[ScoreReason],
    breakdown: _ComponentBreakdown | None = None,
) -> int:
    score = MINERAL_FAT_BASE_SCORE
    compatible_fats = _contains_any(
        text,
        ["aceite de oliva", "mantequilla", "grasa lactea", "coco", "aceite de coco", "manteca de cacao"],
    )
    if compatible_fats:
        delta = 14 if category_id == "oil_or_fat" else 8
        score = _apply_contribution(
            score,
            breakdown,
            "Compatible fat source",
            delta,
            f"Compatible fat source matched '{', '.join(compatible_fats)}' in category {category_id} ({delta:+d}).",
            "compatible_fat_positive",
        )
    for reason in reasons:
        matched = f" Matched: {', '.join(reason.matched_terms)}." if reason.matched_terms else ""
        score = _apply_contribution(
            score,
            breakdown,
            reason.label,
            reason.delta,
            f"{reason.label} rule delta {reason.delta:+d} applied.{matched}",
            reason.rule_id,
        )
    if nutrition.get("calcium_mg") and nutrition.get("phosphorus_mg"):
        calcium = nutrition["calcium_mg"]
        phosphorus = nutrition["phosphorus_mg"]
        if phosphorus > 0 and calcium / phosphorus >= 1:
            score = _apply_contribution(
                score,
                breakdown,
                "Calcium-to-phosphorus ratio bonus",
                10,
                (
                    f"Calcium {_format_amount(calcium)} mg/100 g divided by phosphorus "
                    f"{_format_amount(phosphorus)} mg/100 g = {calcium / phosphorus:.2f}, "
                    "at or above the 1.0 ratio threshold (+10)."
                ),
                "calcium_phosphorus_ratio_positive",
            )
    if category_id == "oil_or_fat":
        seed_oils = _contains_any(text, ["girasol", "soja", "colza", "canola", "maiz"])
        if seed_oils:
            score = _apply_contribution(
                score,
                breakdown,
                "Seed oil in oil category",
                -18,
                (
                    f"Seed-oil source '{', '.join(seed_oils)}' in the oil_or_fat category "
                    "adds the -18 oil-specific penalty."
                ),
                "seed_oil_oil_category_penalty",
            )
    return _clamp_score(score)


def _evidence_quality_score(
    product: Product,
    breakdown: _ComponentBreakdown | None = None,
) -> int:
    score = EVIDENCE_BASE_SCORE
    if not product.ingredients:
        score = _apply_contribution(
            score,
            breakdown,
            "Missing ingredient evidence",
            -35,
            "Ingredients are absent, so ingredient evidence is missing (-35).",
            "missing_ingredients",
        )
    if not product.nutrition_per_100g:
        score = _apply_contribution(
            score,
            breakdown,
            "Missing nutrition evidence",
            -25,
            "Nutrition values are absent, so nutrition evidence is missing (-25).",
            "missing_nutrition",
        )
    if "ingredients" in product.missing_fields:
        score = _apply_contribution(
            score,
            breakdown,
            "Ingredients flagged missing",
            -15,
            "The ingredients field is flagged as missing (-15).",
            "ingredients_missing_field",
        )
    if "nutrition_per_100g" in product.missing_fields:
        score = _apply_contribution(
            score,
            breakdown,
            "Nutrition flagged missing",
            -10,
            "The nutrition_per_100g field is flagged as missing (-10).",
            "nutrition_missing_field",
        )
    if product.ingredient_source is None and product.ingredients:
        score = _apply_contribution(
            score,
            breakdown,
            "Missing ingredient source",
            -5,
            "Ingredients are present but no ingredient source is recorded (-5).",
            "missing_ingredient_source",
        )
    return _clamp_score(score)


def _build_warnings(product: Product, category_confidence: int) -> list[str]:
    warnings = []
    if not product.ingredients:
        warnings.append("Ingredient evidence is missing, so additive and fat-source checks are limited.")
    if not product.nutrition_per_100g:
        warnings.append("Nutrition values are missing, so nutrient balance is estimated from ingredients only.")
    if category_confidence < 50:
        warnings.append("Product category was inferred with low confidence.")
    return warnings


def _apply_framework_caps(
    score: int,
    category_id: str,
    reasons: list[ScoreReason],
    adjustments: list[ScoreContribution] | None = None,
) -> int:
    if any(reason.rule_id == "seed_oils_negative" for reason in reasons):
        limit = 20 if category_id == "oil_or_fat" else 42
        capped_score = min(score, limit)
        if adjustments is not None:
            adjustments.append(
                ScoreContribution(
                    label="Seed-oil framework cap",
                    delta=capped_score - score,
                    detail=(
                        f"Seed-oil framework cap of {limit} applied: "
                        f"score {score} became {capped_score} ({capped_score - score:+d})."
                    ),
                    kind="cap",
                    rule_id="seed_oils_negative",
                )
            )
        return capped_score
    return score


def _component_for_rule(rule_id: str) -> str:
    if rule_id in {"high_sugar_positive", "high_protein_positive"}:
        return "nutrition_profile"
    if rule_id in {"seed_oils_negative", "calcium_phosphorus_positive", "high_fat_without_context_negative"}:
        return "mineral_fat_quality_profile"
    return "ingredient_profile"


def _principle_for_rule(rule_id: str) -> str:
    if "seed_oils" in rule_id:
        return "pufa_avoidance"
    if "calcium" in rule_id or "phosphate" in rule_id:
        return "mineral_balance"
    if "dairy" in rule_id:
        return "dairy_context"
    if "sugar" in rule_id or "fruit" in rule_id:
        return "carbohydrate_context"
    if "protein" in rule_id or "gelatin" in rule_id:
        return "protein_quality"
    return "ingredient_quality"


def _component_by_id(components: list[ScoreComponent], component_id: str) -> ScoreComponent:
    return next(component for component in components if component.id == component_id)


def _has_major_negative(reasons: list[ScoreReason]) -> bool:
    return any(reason.delta <= -12 for reason in reasons)


def _clamp_score(score: float) -> int:
    return max(0, min(100, round(score)))


def _score_band(score: int) -> str:
    if score >= 80:
        return "strong fit"
    if score >= 65:
        return "reasonable fit"
    if score >= 45:
        return "mixed"
    if score >= 25:
        return "weak fit"
    return "avoid"


def _build_comment(
    product: Product,
    score: int,
    band: str,
    reasons: list[ScoreReason],
    category_label: str,
    confidence: int,
    warnings: list[str],
) -> str:
    positives = [reason for reason in reasons if reason.delta > 0]
    negatives = [reason for reason in reasons if reason.delta < 0]

    if not reasons:
        return (
            f"{product.name} scores {score}/100 ({band}) as {category_label.lower()} with "
            f"{confidence}/100 evidence confidence. There is not enough structured nutrition "
            "or ingredient evidence to make a strong Ray Peat-style judgment."
        )

    lead = (
        f"{product.name} scores {score}/100 ({band}) as {category_label.lower()} "
        f"with {confidence}/100 evidence confidence."
    )
    caveat = f" Caveat: {warnings[0]}" if warnings else ""
    if positives and negatives:
        return (
            f"{lead} I would treat it as a mixed product: {positives[0].detail} "
            f"The main concern is that {negatives[0].detail.lower()}{caveat}"
        )
    if positives:
        return f"{lead} From this framework, the product looks relatively favorable: {positives[0].detail}{caveat}"
    return f"{lead} I would be cautious with it: {negatives[0].detail}{caveat}"


def search_and_score(
    query: str,
    max_results: int = 10,
    max_per_source: int = 10,
    min_score: int | None = None,
    max_score: int | None = None,
    sort_by: str = "score",
    providers: list[str] | None = None,
) -> ScoredSearchResults:
    search_results = search_products(query, max_results=max_per_source, providers=providers)
    search_list = list(search_results)
    provider_status = _provider_status_from_search(search_results, providers)

    def fetch_and_score(sr: SearchResult) -> ScoredSearchResult:
        if sr.product_id.startswith("search-"):
            error = "Provider did not return product links; no product evidence available."
            return ScoredSearchResult(search=sr, score=None, error=error)
        try:
            product = require_evidence(fetch_product(sr.url, timeout=10))
            return ScoredSearchResult(search=sr, score=score_product(product))
        except Exception as e:
            return ScoredSearchResult(search=sr, score=None, error=str(e))

    candidates = search_list[:max_results]
    with ThreadPoolExecutor(max_workers=min(4, len(candidates) or 1)) as executor:
        scored = list(executor.map(fetch_and_score, candidates))

    provider_status = _merge_scored_provider_status(
        provider_status,
        scored,
        search_list,
        providers,
    )

    if sort_by == "name":
        scored.sort(key=lambda x: (x.score is None, x.search.display_name.lower()))
    else:
        # Rows without enough evidence to score are still displayed last.
        scored.sort(key=lambda x: (x.score is None, -(x.score.score if x.score else 0)))

    if min_score is not None:
        scored = [s for s in scored if s.score and s.score.score >= min_score]
    if max_score is not None:
        scored = [s for s in scored if s.score and s.score.score <= max_score]

    return ScoredSearchResults(scored[:max_results], provider_status=provider_status)


def _provider_status_from_search(
    search_results: object,
    providers: list[str] | None,
) -> list[ProviderOutcome]:
    status = getattr(search_results, "provider_status", None)
    if status:
        return list(status)

    # Backward compatible fallback for callers/tests that return a plain list.
    order: list[str] = []
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for result in list(search_results or []):
        source = result.source or "Unknown"
        key = source.lower()
        if key not in counts:
            order.append(key)
            counts[key] = 0
            names[key] = source
        counts[key] += 1
    if providers:
        for provider in providers:
            key = provider.lower()
            if provider and key != "all" and key not in order:
                order.append(key)
                names[key] = provider
                counts[key] = 0
    return [
        ProviderOutcome(
            provider=names[key],
            outcome="ok" if counts.get(key) else "empty",
            products=counts.get(key, 0),
        )
        for key in order
    ]


def _merge_scored_provider_status(
    provider_status: list[ProviderOutcome],
    scored: list[ScoredSearchResult],
    search_results: list[SearchResult],
    providers: list[str] | None,
) -> list[ProviderOutcome]:
    ordered: list[str] = []
    status_by_key: dict[str, ProviderOutcome] = {}

    def add(status: ProviderOutcome) -> None:
        key = status.provider.lower()
        if key not in status_by_key:
            ordered.append(key)
            status_by_key[key] = status

    for status in provider_status:
        add(status)
    for result in search_results:
        add(ProviderOutcome(result.source or "Unknown", "empty", 0))
    if providers:
        for provider in providers:
            if provider and provider.lower() != "all":
                add(ProviderOutcome(provider, "empty", 0))

    complete_counts: dict[str, int] = {}
    for row in scored:
        if row.score is not None:
            key = (row.search.source or "Unknown").lower()
            complete_counts[key] = complete_counts.get(key, 0) + 1

    merged: list[ProviderOutcome] = []
    for key in ordered:
        original = status_by_key[key]
        if original.outcome in {"blocked", "error"}:
            merged.append(
                ProviderOutcome(
                    provider=original.provider,
                    outcome=original.outcome,
                    products=0,
                    cause=original.cause,
                )
            )
            continue
        complete = complete_counts.get(key, 0)
        if complete:
            merged.append(ProviderOutcome(original.provider, "ok", complete))
        else:
            merged.append(
                ProviderOutcome(
                    original.provider,
                    "empty",
                    0,
                    original.cause if original.outcome == "empty" else None,
                )
            )
    return merged

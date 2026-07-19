from __future__ import annotations

from .categories import detect_category
from .knowledge_base import load_knowledge_base
from .models import Product, ProductScore, ScoredSearchResult, ScoreComponent, ScoreReason, SearchResult
from .nutrition import normalize_text
from .supermarkets import fetch_product, search_products


COMPONENT_WEIGHTS = {
    "nutrition_profile": 0.30,
    "ingredient_profile": 0.35,
    "processing_profile": 0.15,
    "mineral_fat_quality_profile": 0.15,
    "evidence_quality": 0.05,
}


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
    score = _apply_framework_caps(score, category.id, reasons)
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
        warnings=warnings,
    )


def _build_components(product: Product, category_id: str, reasons: list[ScoreReason]) -> list[ScoreComponent]:
    nutrition = product.nutrition_per_100g
    text = normalize_text(" ".join([product.name, product.description or "", " ".join(product.ingredients)]))
    ingredient_reasons = [r for r in reasons if r.component == "ingredient_profile"]
    nutrition_reasons = [r for r in reasons if r.component == "nutrition_profile"]
    fat_mineral_reasons = [r for r in reasons if r.component == "mineral_fat_quality_profile"]

    processing_score, processing_reasons = _processing_profile_score(product, text)
    components = [
        ScoreComponent(
            id="nutrition_profile",
            label="Nutrition profile",
            score=_nutrition_profile_score(nutrition, category_id),
            weight=COMPONENT_WEIGHTS["nutrition_profile"],
            reasons=nutrition_reasons,
            confidence=80 if nutrition else 25,
        ),
        ScoreComponent(
            id="ingredient_profile",
            label="Ingredient profile",
            score=_ingredient_profile_score(category_id, ingredient_reasons),
            weight=COMPONENT_WEIGHTS["ingredient_profile"],
            reasons=ingredient_reasons,
            confidence=90 if product.ingredients else 30,
        ),
        ScoreComponent(
            id="processing_profile",
            label="Processing profile",
            score=processing_score,
            weight=COMPONENT_WEIGHTS["processing_profile"],
            reasons=processing_reasons,
            confidence=85 if product.ingredients else 25,
        ),
        ScoreComponent(
            id="mineral_fat_quality_profile",
            label="Mineral and fat quality",
            score=_mineral_fat_quality_score(nutrition, text, category_id, fat_mineral_reasons),
            weight=COMPONENT_WEIGHTS["mineral_fat_quality_profile"],
            reasons=fat_mineral_reasons,
            confidence=75 if product.ingredients or nutrition else 25,
        ),
        ScoreComponent(
            id="evidence_quality",
            label="Evidence quality",
            score=_evidence_quality_score(product),
            weight=COMPONENT_WEIGHTS["evidence_quality"],
            reasons=[],
            confidence=100,
        ),
    ]
    return components


def _nutrition_profile_score(nutrition: dict[str, float], category_id: str) -> int:
    if not nutrition:
        return 50

    score = 60
    sugars = nutrition.get("sugars_g")
    protein = nutrition.get("protein_g")
    saturated_fat = nutrition.get("saturated_fat_g")
    salt = nutrition.get("salt_g")
    fiber = nutrition.get("fiber_g")
    calcium = nutrition.get("calcium_mg")

    if sugars is not None:
        if category_id in {"dairy_milk", "dairy_fermented", "dairy_dessert", "fruit_or_juice"}:
            score += 6 if sugars >= 4 else 0
            score -= 8 if sugars > 22 else 0
        else:
            score -= 8 if sugars > 12 else 0
            score -= 8 if sugars > 25 else 0
    if protein is not None:
        score += 8 if protein >= 8 else 4 if protein >= 3 else 0
    if fiber is not None and fiber >= 3:
        score += 3
    if saturated_fat is not None and category_id not in {"cheese", "dairy_milk", "oil_or_fat"}:
        score -= 8 if saturated_fat > 5 else 0
    if salt is not None:
        score -= 10 if salt > 1.5 else 4 if salt > 0.8 else 0
    if calcium is not None and category_id.startswith("dairy"):
        score += 8 if calcium >= 100 else 0

    return _clamp_score(score)


def _ingredient_profile_score(category_id: str, reasons: list[ScoreReason]) -> int:
    score = 62
    if category_id in {"dairy_milk", "dairy_fermented", "cheese"}:
        score += 8
    if category_id == "fruit_or_juice":
        score += 6
    for reason in reasons:
        multiplier = 0.65 if reason.rule_id == "fruit_sugar_positive" and _has_major_negative(reasons) else 1.0
        score += round(reason.delta * multiplier)
    return _clamp_score(score)


def _processing_profile_score(product: Product, text: str) -> tuple[int, list[ScoreReason]]:
    if not product.ingredients:
        return 45, []

    ingredient_count = len(product.ingredients)
    score = 92 if ingredient_count <= 2 else 78 if ingredient_count <= 6 else 60
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
        score += delta
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
        score -= 10
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
) -> int:
    score = 58
    compatible_fats = _contains_any(
        text,
        ["aceite de oliva", "mantequilla", "grasa lactea", "coco", "aceite de coco", "manteca de cacao"],
    )
    if compatible_fats:
        score += 14 if category_id == "oil_or_fat" else 8
    for reason in reasons:
        score += reason.delta
    if nutrition.get("calcium_mg") and nutrition.get("phosphorus_mg"):
        calcium = nutrition["calcium_mg"]
        phosphorus = nutrition["phosphorus_mg"]
        if phosphorus > 0 and calcium / phosphorus >= 1:
            score += 10
    if category_id == "oil_or_fat" and _contains_any(text, ["girasol", "soja", "colza", "canola", "maiz"]):
        score -= 18
    return _clamp_score(score)


def _evidence_quality_score(product: Product) -> int:
    score = 100
    if not product.ingredients:
        score -= 35
    if not product.nutrition_per_100g:
        score -= 25
    if "ingredients" in product.missing_fields:
        score -= 15
    if "nutrition_per_100g" in product.missing_fields:
        score -= 10
    if product.ingredient_source is None and product.ingredients:
        score -= 5
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


def _apply_framework_caps(score: int, category_id: str, reasons: list[ScoreReason]) -> int:
    if any(reason.rule_id == "seed_oils_negative" for reason in reasons):
        return min(score, 20 if category_id == "oil_or_fat" else 42)
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


def _product_from_search_result(search_result: SearchResult, *, fetch_error: str) -> Product:
    name = search_result.display_name
    if not name or name.strip().lower() in {"none", "null", "undefined"}:
        name = search_result.product_id or "Unnamed product"
    return Product(
        name=name,
        source=search_result.source,
        url=search_result.url,
        brand=search_result.brand,
        description=search_result.category,
        ingredients=[],
        nutrition_per_100g={},
        missing_fields=["ingredients", "nutrition_per_100g"],
        raw={
            "search_result": search_result.model_dump(mode="json"),
            "fetch_error": fetch_error,
            "score_basis": "search_result_fallback",
        },
    )


def search_and_score(
    query: str,
    max_results: int = 10,
    max_per_source: int = 10,
    min_score: int | None = None,
    max_score: int | None = None,
    sort_by: str = "score",
    providers: list[str] | None = None,
) -> list[ScoredSearchResult]:
    search_results = search_products(query, max_results=max_per_source, providers=providers)
    scored: list[ScoredSearchResult] = []

    for sr in search_results:
        try:
            product = fetch_product(sr.url)
            score = score_product(product)
            scored.append(ScoredSearchResult(search=sr, score=score))
        except Exception as e:
            fallback_score = score_product(_product_from_search_result(sr, fetch_error=str(e)))
            scored.append(ScoredSearchResult(search=sr, score=fallback_score, error=str(e)))

        if len(scored) >= max_results:
            break

    if sort_by == "name":
        scored.sort(key=lambda x: x.search.display_name.lower())
    else:
        scored.sort(key=lambda x: x.score.score if x.score else 0, reverse=True)

    if min_score is not None:
        scored = [s for s in scored if s.score and s.score.score >= min_score]
    if max_score is not None:
        scored = [s for s in scored if s.score and s.score.score <= max_score]

    return scored[:max_results]

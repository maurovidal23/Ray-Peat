from __future__ import annotations

from .knowledge_base import load_knowledge_base
from .models import Product, ProductScore, ScoreReason
from .nutrition import normalize_text


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
    reasons: list[ScoreReason] = []
    score = int(knowledge.get("base_score", 50))

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

        score += delta
        detail = rule["detail"]
        if matched:
            detail = f"{detail} Detected: {', '.join(matched)}."
        reasons.append(
            ScoreReason(
                rule_id=rule_id,
                label=rule["label"],
                delta=delta,
                detail=detail,
            )
        )

    score = max(0, min(100, score))
    band = _score_band(score)
    comment = _build_comment(product, score, band, reasons)
    return ProductScore(score=score, band=band, comment=comment, reasons=reasons, product=product)


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


def _build_comment(product: Product, score: int, band: str, reasons: list[ScoreReason]) -> str:
    positives = [reason for reason in reasons if reason.delta > 0]
    negatives = [reason for reason in reasons if reason.delta < 0]

    if not reasons:
        return (
            f"{product.name} scores {score}/100 ({band}). There is not enough structured "
            "nutrition or ingredient evidence to make a strong Ray Peat-style judgment."
        )

    lead = f"{product.name} scores {score}/100 ({band})."
    if positives and negatives:
        return (
            f"{lead} I would treat it as a mixed product: {positives[0].detail} "
            f"The main concern is that {negatives[0].detail.lower()}"
        )
    if positives:
        return f"{lead} From this framework, the product looks relatively favorable: {positives[0].detail}"
    return f"{lead} I would be cautious with it: {negatives[0].detail}"


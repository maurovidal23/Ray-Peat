from __future__ import annotations

from .models import Product, ProductCategory
from .nutrition import normalize_text


CATEGORY_LABELS = {
    "dairy_milk": "Milk",
    "dairy_fermented": "Fermented dairy",
    "cheese": "Cheese",
    "dairy_dessert": "Dairy dessert",
    "fruit_or_juice": "Fruit or juice",
    "sweetened_beverage": "Sweetened beverage",
    "water": "Water",
    "oil_or_fat": "Oil or fat",
    "meat_red": "Red meat",
    "meat_poultry": "Poultry",
    "fish_or_seafood": "Fish or seafood",
    "starch_or_cereal": "Starch or cereal",
    "confectionery": "Confectionery",
    "prepared_meal": "Prepared meal",
    "sauce_or_condiment": "Sauce or condiment",
    "unknown": "Unknown",
}


KEYWORDS = {
    "dairy_milk": ["leche entera", "leche semidesnatada", "leche desnatada", "leche"],
    "dairy_fermented": ["yogur", "yoghurt", "kefir", "cuajada"],
    "cheese": ["queso", "mozzarella", "cheddar", "gouda", "emmental", "parmesano"],
    "dairy_dessert": ["natillas", "flan", "arroz con leche", "postre lacteo"],
    "fruit_or_juice": ["zumo", "fruta", "naranja", "manzana", "uva", "melocoton", "pera"],
    "water": ["agua mineral", "agua"],
    "oil_or_fat": ["aceite", "mantequilla", "margarina", "grasa", "manteca"],
    "meat_red": ["ternera", "vacuno", "cerdo", "jamon", "chorizo", "salchichon"],
    "meat_poultry": ["pollo", "pavo"],
    "fish_or_seafood": ["pescado", "merluza", "atun", "sardina", "gamba", "mejillon"],
    "starch_or_cereal": ["pan", "galleta", "cereal", "pasta", "arroz", "harina", "patata"],
    "confectionery": ["chocolate", "caramelo", "gominola", "bombon", "helado"],
    "prepared_meal": ["pizza", "lasana", "croqueta", "empanada", "plato preparado"],
    "sauce_or_condiment": ["salsa", "mayonesa", "ketchup", "mostaza"],
    "sweetened_beverage": ["refresco", "cola", "bebida", "limonada", "gaseosa"],
}


def detect_category(product: Product) -> ProductCategory:
    source_parts = [
        product.name,
        product.description or "",
        product.raw.get("category") or "",
        product.raw.get("categories") or "",
    ]
    weak_text = normalize_text(" ".join(str(part) for part in source_parts if part))
    ingredient_text = normalize_text(" ".join(product.ingredients))
    combined = f"{weak_text} {ingredient_text}".strip()

    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for category_id, terms in KEYWORDS.items():
        for term in terms:
            normalized_term = normalize_text(term)
            if normalized_term in ingredient_text:
                scores[category_id] = scores.get(category_id, 0) + 3
                evidence.setdefault(category_id, []).append(f"ingredient: {term}")
            elif normalized_term in weak_text:
                scores[category_id] = scores.get(category_id, 0) + 2
                evidence.setdefault(category_id, []).append(f"name/category: {term}")

    if not scores:
        return ProductCategory(id="unknown", label=CATEGORY_LABELS["unknown"], confidence=20, evidence=[])

    category_id = max(scores, key=scores.get)
    confidence = min(95, 35 + scores[category_id] * 15)

    if category_id == "dairy_milk" and any(term in combined for term in ["yogur", "kefir"]):
        category_id = "dairy_fermented"
    if category_id == "oil_or_fat" and "margarina" in combined:
        confidence = max(confidence, 80)

    return ProductCategory(
        id=category_id,
        label=CATEGORY_LABELS[category_id],
        confidence=confidence,
        evidence=evidence.get(category_id, [])[:4],
    )

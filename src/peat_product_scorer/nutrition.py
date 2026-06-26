from __future__ import annotations

import re
import unicodedata


NUTRIENT_ALIASES = {
    "energy_kcal": ["kcal", "energia", "valor energetico"],
    "fat_g": ["grasas", "grasa"],
    "saturated_fat_g": ["saturadas", "acidos grasos saturados"],
    "carbohydrate_g": ["hidratos de carbono", "carbohidratos"],
    "sugars_g": ["azucares", "azucar"],
    "fiber_g": ["fibra alimentaria", "fibra"],
    "protein_g": ["proteinas", "proteina"],
    "salt_g": ["sal"],
    "calcium_mg": ["calcio"],
    "phosphorus_mg": ["fosforo"],
    "iron_mg": ["hierro"],
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value.lower()).strip()


def split_ingredients(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r",|;|\n", value)
    return [part.strip(" .") for part in parts if part and part.strip(" .")]


def canonical_nutrient_name(label: str) -> str | None:
    normalized = normalize_text(label)
    for canonical, aliases in NUTRIENT_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def parse_numeric_amount(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    match = re.search(r"[-+]?\d+(?:[,.]\d+)?", value)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def normalize_nutrition(raw: dict[str, object]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for label, value in raw.items():
        canonical = canonical_nutrient_name(str(label))
        amount = parse_numeric_amount(value if isinstance(value, int | float | str) else str(value))
        if canonical and amount is not None:
            normalized[canonical] = amount
    return normalized

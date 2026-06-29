from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class Product(BaseModel):
    name: str
    source: str | None = None
    url: HttpUrl | None = None
    brand: str | None = None
    description: str | None = None
    ingredient_text: str | None = None
    ingredient_source: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    nutrition_per_100g: dict[str, float] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class ScoreReason(BaseModel):
    rule_id: str
    label: str
    delta: int
    detail: str


class ProductScore(BaseModel):
    score: int
    band: str
    comment: str
    reasons: list[ScoreReason]
    product: Product

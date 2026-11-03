from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

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
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SearchResult(BaseModel):
    source: str
    query: str
    display_name: str
    product_id: str
    url: str
    brand: str | None = None
    price: float | None = None
    price_currency: str | None = None
    thumbnail: str | None = None
    category: str | None = None


class ScoreReason(BaseModel):
    rule_id: str
    label: str
    delta: int
    detail: str
    component: str | None = None
    principle: str | None = None
    evidence_type: str | None = None
    matched_terms: list[str] = Field(default_factory=list)


class ScoreContribution(BaseModel):
    label: str
    delta: int
    detail: str
    kind: Literal["adjustment", "cap"] = "adjustment"
    rule_id: str | None = None


class ScoreComponent(BaseModel):
    id: str
    label: str
    score: int
    weight: float
    reasons: list[ScoreReason] = Field(default_factory=list)
    confidence: int = 100
    base_score: int
    contributions: list[ScoreContribution] = Field(default_factory=list)


class ProductCategory(BaseModel):
    id: str
    label: str
    confidence: int
    evidence: list[str] = Field(default_factory=list)


class ProductScore(BaseModel):
    score: int
    band: str
    comment: str
    reasons: list[ScoreReason]
    product: Product
    confidence: int = 100
    category: ProductCategory | None = None
    components: list[ScoreComponent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    score_adjustments: list[ScoreContribution] = Field(default_factory=list)


class ScoredSearchResult(BaseModel):
    search: SearchResult
    score: ProductScore | None = None
    error: str | None = None

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

ProviderOutcomeStatus = Literal["ok", "empty", "blocked", "error"]


@dataclass(frozen=True, eq=False)
class ProviderOutcome:
    """Structured outcome for one provider search.

    ``products`` is the number of products available to the scoring pipeline.
    ``cause`` is only relevant for non-``ok`` outcomes (HTTP status, captcha or
    anti-bot marker, or exception type and message).
    """

    provider: str
    outcome: ProviderOutcomeStatus
    products: int = 0
    cause: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "outcome": self.outcome,
            "products": self.products,
        }
        if self.outcome != "ok" and self.cause:
            payload["cause"] = self.cause
        return payload

    def model_dump(self, *, mode: str = "json", exclude_none: bool = False) -> dict[str, Any]:
        """Keep the outcome easy to serialize alongside pydantic API models."""
        del mode, exclude_none
        return self.to_dict()

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ProviderOutcome):
            return (
                self.provider,
                self.outcome,
                self.products,
                self.cause,
            ) == (
                other.provider,
                other.outcome,
                other.products,
                other.cause,
            )
        if isinstance(other, dict):
            return self.to_dict() == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.provider, self.outcome, self.products, self.cause))


class ProviderSearchOutcome(list):
    """List-compatible provider search result with its own outcome metadata.

    Existing callers can still iterate, index and length-check the search like a
    plain list. ``outcome``/``products``/``cause`` expose the structured result
    that is aggregated by :func:`search_products`.
    """

    def __init__(
        self,
        results: list[SearchResult] | tuple[SearchResult, ...] = (),
        *,
        provider: str,
        outcome: ProviderOutcomeStatus = "empty",
        products: int | None = None,
        cause: str | None = None,
    ) -> None:
        super().__init__(results)
        self.provider = provider
        self.outcome = outcome
        self.products = len(self) if products is None else max(0, products)
        self.cause = cause

    def status(self) -> ProviderOutcome:
        return ProviderOutcome(
            provider=self.provider,
            outcome=self.outcome,
            products=self.products,
            cause=self.cause,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.status().to_dict()


class SearchResults(list):
    """Search result list carrying the aggregated per-provider status."""

    def __init__(
        self,
        results: list[SearchResult] | tuple[SearchResult, ...] = (),
        *,
        provider_status: list[ProviderOutcome] | None = None,
    ) -> None:
        super().__init__(results)
        self.provider_status = list(provider_status or [])

    @property
    def outcomes(self) -> list[ProviderOutcome]:
        return self.provider_status

    @property
    def results(self) -> list[SearchResult]:
        return list(self)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key == "results":
                return list(self)
            if key in {"provider_status", "outcomes"}:
                return self.provider_status
            raise KeyError(key)
        return super().__getitem__(key)

    def keys(self) -> tuple[str, str]:
        return ("results", "provider_status")


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


class ScoredSearchResults(list):
    """Scored result list carrying aggregated per-provider search status."""

    def __init__(
        self,
        results: list[ScoredSearchResult] | tuple[ScoredSearchResult, ...] = (),
        *,
        provider_status: list[ProviderOutcome] | None = None,
    ) -> None:
        super().__init__(results)
        self.provider_status = list(provider_status or [])

    @property
    def outcomes(self) -> list[ProviderOutcome]:
        return self.provider_status

    @property
    def results(self) -> list[ScoredSearchResult]:
        return list(self)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key == "results":
                return list(self)
            if key in {"provider_status", "outcomes"}:
                return self.provider_status
            raise KeyError(key)
        return super().__getitem__(key)

    def keys(self) -> tuple[str, str]:
        return ("results", "provider_status")

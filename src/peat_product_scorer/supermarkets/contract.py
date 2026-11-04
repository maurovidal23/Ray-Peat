from __future__ import annotations

import ipaddress
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse

from ..models import (
    Product,
    ProviderOutcome,
    ProviderOutcomeStatus,
    ProviderSearchOutcome,
    SearchResult,
    SearchResults,
)

BLOCKED_STATUS_CODES = frozenset({403, 429})
ANTI_BOT_MARKERS = (
    "captcha",
    "access denied",
    "unusual traffic",
    "are you a robot",
    "bot detected",
    "request blocked",
    "cloudflare",
    "akamai",
)

# Guardrail keys are matched exactly. Nutrition normalization stores total
# carbohydrate as carbohydrate_g; that key does not satisfy carbs_g.
GUARDRAIL_NUTRIENT_KEYS = (
    "sugars_g",
    "protein_g",
    "fat_g",
    "saturated_fat_g",
    "salt_g",
    "carbs_g",
)


@dataclass(frozen=True)
class GuardrailResult:
    ok: bool
    missing: tuple[str, ...] = ()


class ProviderEvidenceError(Exception):
    """Raised when a provider cannot supply enough evidence to score a product."""

    def __init__(self, message: str = "", *, missing: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.missing = missing


@dataclass(frozen=True)
class EvidenceGuardrail:
    nutrient_keys: tuple[str, ...] = GUARDRAIL_NUTRIENT_KEYS
    min_nutrients: int = 4

    def check(self, product: Product) -> GuardrailResult:
        missing: list[str] = []
        ingredients = product.ingredients or []
        if not any(str(ingredient).strip() for ingredient in ingredients):
            missing.append("ingredients")

        nutrition = product.nutrition_per_100g or {}
        present = 0
        for key in self.nutrient_keys:
            if not _is_finite_number(nutrition.get(key)):
                missing.append(key)
            else:
                present += 1

        has_ingredients = "ingredients" not in missing
        ok = has_ingredients and present >= self.min_nutrients
        return GuardrailResult(ok=ok, missing=tuple(missing))


def check_guardrail(product: Product) -> GuardrailResult:
    return EvidenceGuardrail().check(product)


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return math.isfinite(value)


def blocked_cause_for_response(response: object) -> str | None:
    """Return a blocked cause when a response shows HTTP or anti-bot blocking."""
    status_code = getattr(response, "status_code", None)
    if status_code in BLOCKED_STATUS_CODES:
        return f"HTTP {status_code}"
    try:
        text = str(getattr(response, "text", "") or "")
    except Exception:
        text = ""
    lowered = text.lower()
    for marker in ANTI_BOT_MARKERS:
        if marker in lowered:
            return f"captcha/anti-bot marker: {marker}"
    return None


def classify_provider_failure(
    error: BaseException,
    *,
    response: object | None = None,
) -> tuple[ProviderOutcomeStatus, str]:
    """Classify a provider exception as ``blocked`` or ``error`` with its cause."""
    resolved_response = response if response is not None else getattr(error, "response", None)
    blocked_cause = blocked_cause_for_response(resolved_response)
    if blocked_cause:
        return "blocked", blocked_cause
    message = str(error).strip()
    cause = f"{type(error).__name__}: {message}" if message else type(error).__name__
    return "error", cause


def validate_provider_url(url: str, domains: tuple[str, ...]) -> None:
    """Reject URLs that escape the provider allowlist or use unsafe components."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Product URL must use HTTP or HTTPS and include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Product URL must not contain credentials.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Product URL has an invalid port.") from exc
    if port is not None and port != {"http": 80, "https": 443}[parsed.scheme.lower()]:
        raise ValueError("Product URL must not use a nonstandard port.")

    hostname = parsed.hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Product URL must not use an IP address.")
    supported_domains = {domain.lower().rstrip(".") for domain in domains}
    if not any(
        hostname == domain or hostname.endswith(f".{domain}") for domain in supported_domains
    ):
        raise ValueError("Product URL hostname is not a supported supermarket.")


def require_evidence(product: Product, *, source: str | None = None) -> Product:
    """Return ``product`` when it satisfies the guardrail, otherwise raise."""
    result = check_guardrail(product)
    if result.ok:
        return product
    label = source or product.source or "Product"
    raise ProviderEvidenceError(
        f"{label} evidence incomplete: missing {', '.join(result.missing)}.",
        missing=result.missing,
    )


class ProductProvider(ABC):
    """Common contract implemented by every supermarket data provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @property
    @abstractmethod
    def domains(self) -> tuple[str, ...]:
        """Domains the provider is allowed to search and fetch."""

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Return product search results for a query."""

    @abstractmethod
    def fetch(self, url: str, timeout: int = 20) -> Product:
        """Fetch and normalize a single product page."""

    def fetch_and_validate(self, url: str, timeout: int = 20) -> Product:
        validate_provider_url(url, self.domains)
        return require_evidence(self.fetch(url, timeout=timeout), source=self.name)

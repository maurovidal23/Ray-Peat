from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SupermarketAdapter:
    name: str
    domains: tuple[str, ...]

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        return any(host == domain or host.endswith(f".{domain}") for domain in self.domains)


ADAPTERS = (
    SupermarketAdapter("Mercadona", ("mercadona.es",)),
    SupermarketAdapter("DIA", ("dia.es",)),
    SupermarketAdapter("Alcampo", ("alcampo.es",)),
    SupermarketAdapter("Consum", ("consum.es",)),
    SupermarketAdapter("Eroski", ("eroski.es",)),
)

# Every domain recognized by at least one adapter, in adapter declaration order.
SUPPORTED_DOMAINS = tuple(domain for adapter in ADAPTERS for domain in adapter.domains)


def supermarket_name_for_url(url: str) -> str:
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter.name
    return "Unknown supermarket"

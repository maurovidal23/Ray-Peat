from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SupermarketAdapter:
    name: str
    domains: tuple[str, ...]

    def matches(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(domain in host for domain in self.domains)


ADAPTERS = (
    SupermarketAdapter("Mercadona", ("mercadona.es",)),
    SupermarketAdapter("Carrefour Espana", ("carrefour.es",)),
    SupermarketAdapter("DIA", ("dia.es",)),
    SupermarketAdapter("Alcampo", ("alcampo.es",)),
    SupermarketAdapter("Consum", ("consum.es",)),
    SupermarketAdapter("El Corte Ingles", ("elcorteingles.es",)),
    SupermarketAdapter("Eroski", ("eroski.es",)),
)


def supermarket_name_for_url(url: str) -> str:
    for adapter in ADAPTERS:
        if adapter.matches(url):
            return adapter.name
    return "Unknown supermarket"

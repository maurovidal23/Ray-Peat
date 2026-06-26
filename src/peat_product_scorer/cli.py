from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .models import Product
from .nutrition import normalize_nutrition, split_ingredients
from .scorer import score_product
from .supermarkets import fetch_product

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("score-file")
def score_file(path: Path) -> None:
    """Score a local product JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    product = _product_from_payload(payload)
    _print_score(score_product(product))


@app.command("score-url")
def score_url(url: str) -> None:
    """Fetch a supermarket product page and score it."""
    product = fetch_product(url)
    _print_score(score_product(product))


def _product_from_payload(payload: dict) -> Product:
    nutrition = payload.get("nutrition_per_100g") or payload.get("nutrition") or {}
    return Product(
        name=payload["name"],
        source=payload.get("source"),
        url=payload.get("url"),
        brand=payload.get("brand"),
        description=payload.get("description"),
        ingredients=split_ingredients(payload.get("ingredients")),
        nutrition_per_100g=normalize_nutrition(nutrition),
        raw=payload,
    )


def _print_score(result) -> None:
    console.print(f"[bold]{result.product.name}[/bold]")
    console.print(f"Score: [bold]{result.score}/100[/bold] ({result.band})")
    console.print(result.comment)

    table = Table("Rule", "Delta", "Reason")
    for reason in result.reasons:
        table.add_row(reason.label, f"{reason.delta:+d}", reason.detail)
    console.print(table)

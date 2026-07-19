from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .models import Product
from .nutrition import normalize_nutrition, split_ingredients
from .scorer import score_product, search_and_score
from .supermarkets import fetch_product, search_products, search_dia_products, search_mercadona_products

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


@app.command("search")
def search(
    query: str,
    source: str = typer.Option("all", help="Supermarket source: dia, mercadona, or all"),
    max_results: int = typer.Option(10, help="Maximum results to return"),
) -> None:
    """Search for products across supermarkets."""
    if source == "dia":
        results = search_dia_products(query, max_results)
    elif source == "mercadona":
        results = search_mercadona_products(query, max_results)
    else:
        results = search_products(query, max_results)

    if not results:
        console.print("[yellow]No products found.[/yellow]")
        raise typer.Exit()

    table = Table("Source", "Product", "Brand", "Price", "URL")
    for r in results:
        price_str = f"{r.price} {r.price_currency or ''}" if r.price else "-"
        table.add_row(r.source, r.display_name, r.brand or "-", price_str, r.url)
    console.print(table)
    console.print(f"[dim]{len(results)} results for '{query}'[/dim]")


@app.command("search-score")
def search_score(
    query: str,
    max_results: int = typer.Option(10, help="Maximum results to return"),
    min_score: int = typer.Option(None, help="Minimum score filter (0-100)"),
    sort_by: str = typer.Option("score", help="Sort order: score or name"),
) -> None:
    """Search for products, fetch details, and score each one."""
    scored = search_and_score(query, max_results=max_results, max_per_source=max_results, min_score=min_score, sort_by=sort_by)

    if not scored:
        console.print("[yellow]No products found or scored.[/yellow]")
        raise typer.Exit()

    table = Table("Score", "Band", "Source", "Product", "Brand", "Price", "Error")
    table.add_column(no_wrap=True)
    for sr in scored:
        score_str = f"{sr.score.score}" if sr.score else "-"
        band_str = sr.score.band if sr.score else "-"
        error_str = sr.error[:50] if sr.error else ""
        price_str = f"{sr.search.price} {sr.search.price_currency or ''}" if sr.search.price else "-"
        table.add_row(
            f"[bold]{score_str}[/bold]",
            band_str,
            sr.search.source,
            sr.search.display_name[:50],
            sr.search.brand or "-",
            price_str,
            error_str,
        )
    console.print(table)

    if scored and scored[0].score:
        console.print(f"\n[bold]Top result:[/bold] {scored[0].score.product.name}")
        console.print(f"Score: [bold]{scored[0].score.score}/100[/bold] ({scored[0].score.band})")
        console.print(scored[0].score.comment)


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

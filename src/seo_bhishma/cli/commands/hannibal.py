"""Hannibal CLI: URL cannibalization detection from GSC data."""

from __future__ import annotations

from datetime import datetime

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.core.hannibal import detect_cannibalization
from seo_bhishma.models.hannibal import CannibalizationConfig


@click.command()
@click.option("--input-csv", default=None, help="Path to the GSC input CSV file")
@click.option("--output-csv", default=None, help="Path to save the cannibalization report")
@click.option(
    "--exact-match-threshold",
    default=None,
    type=float,
    help="Threshold for exact match query ratio",
)
@click.option(
    "--impression-share-threshold",
    default=None,
    type=float,
    help="Threshold for impression share of exact match queries",
)
@click.option(
    "--click-share-threshold",
    default=None,
    type=float,
    help="Threshold for click share of exact match queries",
)
@click.option(
    "--query-share-threshold", default=None, type=float, help="Threshold for query share"
)
@click.option("--use-slug-similarity", is_flag=True, default=False, help="Enable slug similarity")
@click.option(
    "--slug-similarity-threshold",
    default=None,
    type=float,
    help="Slug similarity threshold (used when --use-slug-similarity is set)",
)
@click.option(
    "--use-semantic-check", is_flag=True, default=False, help="Enable semantic similarity check"
)
def hannibal(
    input_csv: str | None,
    output_csv: str | None,
    exact_match_threshold: float | None,
    impression_share_threshold: float | None,
    click_share_threshold: float | None,
    query_share_threshold: float | None,
    use_slug_similarity: bool,
    slug_similarity_threshold: float | None,
    use_semantic_check: bool,
) -> None:
    """Identify URL cannibalization issues using GSC data."""
    console.print(
        tool_panel("Hannibal", "Identify URL cannibalization issues using GSC data.")
    )

    defaults = CannibalizationConfig()

    if not input_csv:
        input_csv = Prompt.ask("[cyan]Enter the input CSV file[/cyan]", default="input.csv")
    if exact_match_threshold is None:
        exact_match_threshold = float(
            Prompt.ask(
                "[cyan]Threshold for exact match query ratio[/cyan]",
                default=str(defaults.exact_match_threshold),
            )
        )
    if impression_share_threshold is None:
        impression_share_threshold = float(
            Prompt.ask(
                "[cyan]Threshold for impression share[/cyan]",
                default=str(defaults.impression_share_threshold),
            )
        )
    if click_share_threshold is None:
        click_share_threshold = float(
            Prompt.ask(
                "[cyan]Threshold for click share[/cyan]",
                default=str(defaults.click_share_threshold),
            )
        )
    if query_share_threshold is None:
        query_share_threshold = float(
            Prompt.ask(
                "[cyan]Threshold for query share[/cyan]",
                default=str(defaults.query_share_threshold),
            )
        )
    if not use_slug_similarity:
        use_slug_similarity = Prompt.ask(
            "[cyan]Enable URL slug similarity check?[/cyan]",
            choices=["yes", "no"],
            default="no",
        ) == "yes"
    if use_slug_similarity and slug_similarity_threshold is None:
        slug_similarity_threshold = float(
            Prompt.ask(
                "[cyan]Slug similarity threshold[/cyan]",
                default=str(defaults.slug_similarity_threshold),
            )
        )
    if not use_semantic_check:
        use_semantic_check = Prompt.ask(
            "[cyan]Enable semantic check?[/cyan]", choices=["yes", "no"], default="no"
        ) == "yes"

    config = CannibalizationConfig(
        exact_match_threshold=exact_match_threshold,
        impression_share_threshold=impression_share_threshold,
        click_share_threshold=click_share_threshold,
        query_share_threshold=query_share_threshold,
        use_slug_similarity=use_slug_similarity,
        slug_similarity_threshold=(
            slug_similarity_threshold
            if slug_similarity_threshold is not None
            else defaults.slug_similarity_threshold
        ),
        use_semantic_check=use_semantic_check,
    )

    if not output_csv:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_csv = f"cannibalization_report_{timestamp}.csv"

    console.print("\n[green][+] Starting cannibalization detection...[/green]")

    try:
        with make_progress() as progress:
            task = progress.add_task("[+] Analyzing pages...", total=None)

            def on_progress(completed: int, total: int) -> None:
                progress.update(task, total=total, completed=completed)

            report = detect_cannibalization(input_csv, config=config, on_progress=on_progress)
    except Exception as e:
        console.print(f"[bold red][-] Cannibalization detection failed: {e}[/bold red]")
        return

    df = pd.DataFrame([e.model_dump() for e in report.entries])
    df.to_csv(output_csv, index=False, encoding="utf-8")
    console.print(f"[bold green][+] Cannibalization report saved to {output_csv}[/bold green]")
    console.print(
        f"[green][+] {len(report.entries)} entries across {report.total_clusters} "
        f"clusters from {report.total_pages_analyzed} pages.[/green]\n"
    )

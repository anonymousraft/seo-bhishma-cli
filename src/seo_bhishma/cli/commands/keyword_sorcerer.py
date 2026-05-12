"""Keyword Sorcerer CLI: cluster keywords with OpenAI embeddings + sklearn."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
import pandas as pd
import yaml
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.config.settings import Settings
from seo_bhishma.core.keyword_sorcerer import (
    cluster_keywords,
    estimate_token_usage,
    generate_embeddings,
)
from seo_bhishma.models.keyword_sorcerer import ClusterMethod

# Legacy per-working-directory file kept only as a fallback for users who set
# their key here before the wizard existed. New keys belong in the system-wide
# config file via `seo-bhishma config set openai_api_key ...`.
_CONFIG_FILE = "config.yaml"

_METHOD_BY_CHOICE = {
    "1": ClusterMethod.KMEANS,
    "2": ClusterMethod.AGGLOMERATIVE,
    "3": ClusterMethod.DBSCAN,
    "4": ClusterMethod.SPECTRAL,
}


def _load_config() -> dict:
    path = Path(_CONFIG_FILE)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config(config: dict) -> None:
    with Path(_CONFIG_FILE).open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


@click.command()
def keyword_sorcerer() -> None:
    """Cluster keywords based on semantic relevance."""
    config = _load_config()

    while True:
        console.print(
            tool_panel("Keyword Sorcerer", "Keyword clusterizer powered by OpenAI.")
        )
        console.print("[cyan]1. Cluster keywords with KMeans[/cyan]")
        console.print("[cyan]2. Cluster keywords with Agglomerative Clustering[/cyan]")
        console.print("[cyan]3. Cluster keywords with DBSCAN[/cyan]")
        console.print("[cyan]4. Cluster keywords with Spectral Clustering[/cyan]")
        console.print("[red bold]0. Exit[/red bold]")
        choice = Prompt.ask(
            "[cyan bold]Enter your choice[/cyan bold]",
            choices=["0", "1", "2", "3", "4"],
            default="0",
        )

        if choice == "0":
            console.print("[red bold]Exiting Keyword Sorcerer. Goodbye![/red bold]")
            return

        method = _METHOD_BY_CHOICE[choice]
        input_file = Prompt.ask(
            "[cyan]Enter the path to the input CSV file[/cyan]", default="keywords.csv"
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Prompt.ask(
            "[cyan]Enter the path to the output CSV file[/cyan]",
            default=f"clusters_{timestamp}.csv",
        )

        # Prefer the system-wide config (set via wizard or env) over the legacy local file.
        api_key = Settings().openai_api_key or config.get("api_key", "")
        if not api_key:
            console.print(
                "[dim]Tip: run [bold]seo-bhishma config set openai_api_key ...[/bold] "
                "to store this key system-wide for all tools.[/dim]"
            )
            api_key = Prompt.ask("[cyan]Enter your OpenAI API key[/cyan]", password=True)
            # Persist to the legacy file for backward compatibility (wizard users won't hit this).
            config["api_key"] = api_key
            _save_config(config)

        try:
            df = pd.read_csv(input_file)
        except Exception as e:
            console.print(f"[red][-] Failed to read keywords: {e}[/red]")
            continue
        if "keywords" not in df.columns:
            console.print(
                "[red][-] Input CSV must contain a 'keywords' column.[/red]"
            )
            continue

        keywords = df["keywords"].dropna().astype(str).tolist()
        total_tokens = estimate_token_usage(keywords)
        estimated_cost = (total_tokens / 1000) * 0.02
        console.print(f"[green]Estimated token usage: {total_tokens}[/green]")
        console.print(f"[green]Estimated cost: ${estimated_cost:.4f}[/green]")
        if Prompt.ask("[cyan]Proceed?[/cyan]", choices=["yes", "no"], default="no") != "yes":
            console.print("[red][-] Operation cancelled.[/red]")
            continue

        console.print("[green bold][+] Generating embeddings...[/green bold]")
        with make_progress() as progress:
            task = progress.add_task("[+] Embedding keywords...", total=len(keywords))

            def on_progress(completed: int, total: int) -> None:
                progress.update(task, completed=completed, total=total)

            try:
                embeddings = generate_embeddings(keywords, api_key, on_progress=on_progress)
            except Exception as e:
                console.print(f"[red][-] Embedding generation failed: {e}[/red]")
                continue

        if not any(embeddings):
            console.print(
                "[red][-] All embeddings are empty. Check your input data or API key.[/red]"
            )
            continue

        console.print("[green bold][+] Clustering keywords...[/green bold]")
        try:
            result = cluster_keywords(keywords, embeddings, method=method)
        except Exception as e:
            console.print(f"[red][-] Clustering failed: {e}[/red]")
            continue

        df = df.assign(
            keyword_theme=[result.cluster_names[label] for label in result.labels],
            confidence_score=[result.silhouette_score] * len(result.labels),
        )
        df.to_csv(output_file, index=False, encoding="utf-8")
        console.print(
            f"[green bold][+] Clustered {len(keywords)} keywords into "
            f"{result.num_clusters} clusters. Saved to {output_file}[/green bold]"
        )

        console.print("\n" + "=" * 50 + "\n")

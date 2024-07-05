import click
from art import text2art
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from seo_bhishma_cli import link_sniper, site_mapper, index_spy, sitemap_generator, keyword_sorcerer, gsc_probe, redirection_genius
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR

console = Console()

@click.group(invoke_without_command=True)
@click.version_option(version=CLI_VERSION, prog_name=CLI_NAME)
@click.pass_context
def cli(ctx):
    try:
        ascii_art = text2art(CLI_NAME, font='small')
        console.print(f"[bold bright_cyan]{ascii_art}[/bold bright_cyan]")
        console.print(f"[bold green]Welcome to {CLI_NAME}![/bold green]")
        console.print(f"[green]Version: {CLI_VERSION}[/green]")
        console.print(f"[green]Author: {CLI_AUTHOR}\n[/green]")
        console.print(f"[dim white]This tool is my way of giving back to the community.[/dim white]")
        console.print(f"[dim white]Support: [underline]https://buymeacoffee.com/rathorehitendra[/underline][/dim white]\n")

        if ctx.invoked_subcommand is None:
            ctx.invoke(menu)
    except Exception as e:
        console.print(f"[bold red]An error occurred: {e}[/bold red]")

@click.command()
@click.pass_context
def menu(ctx):
    while True:
        try:
            table = Table(show_header=False, box=None)
            table.add_row("[bold magenta]1.[/bold magenta]", "[yellow]LinkSniper - Check Backlinks[/yellow]")
            table.add_row("[bold magenta]2.[/bold magenta]", "[yellow]SiteMapper - Download Sitemap[/yellow]")
            table.add_row("[bold magenta]3.[/bold magenta]", "[yellow]IndexSpy - Bulk Indexing Checker[/yellow]")
            table.add_row("[bold magenta]4.[/bold magenta]", "[yellow]Sitemap Generator - Generate sitemap from List of URLs[/yellow]")
            table.add_row("[bold magenta]5.[/bold magenta]", "[yellow]Keyword Sorcerer - Keyword Clusteriser[/yellow]")
            table.add_row("[bold magenta]6.[/bold magenta]", "[yellow]GSC Probe - Extract GSC Data[/yellow]")
            table.add_row("[bold magenta]7.[/bold magenta]", "[yellow]Redirection Genius - Powerful NLP based URL mapper[/yellow]")
            table.add_row("[bold red]0.[/bold red]", "[red]Exit[/red]")
            
            console.print(table)

            choice = Prompt.ask("[bold cyan]Enter your choice[/bold cyan]", choices=["1", "2", "3", "4", "5", "6", "7", "0"])

            if choice == "1":
                ctx.invoke(link_sniper)
            elif choice == "2":
                ctx.invoke(site_mapper)
            elif choice == "3":
                ctx.invoke(index_spy)
            elif choice == "4":
                ctx.invoke(sitemap_generator)
            elif choice == "5":
                ctx.invoke(keyword_sorcerer)
            elif choice == "6":
                ctx.invoke(gsc_probe)
            elif choice == "7":
                ctx.invoke(redirection_genius)
            elif choice == "0":
                console.print(f"[bold red]Exiting {CLI_NAME}. Goodbye![/bold red]")
                break
        except Exception as e:
            console.print(f"[bold red]An error occurred: {e}[/bold red]")

cli.add_command(menu)
cli.add_command(link_sniper)
cli.add_command(site_mapper)
cli.add_command(index_spy)
cli.add_command(sitemap_generator)
cli.add_command(keyword_sorcerer)
cli.add_command(gsc_probe)
cli.add_command(redirection_genius)

if __name__ == "__main__":
    cli()

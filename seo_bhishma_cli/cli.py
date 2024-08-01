import click
from art import text2art
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table
from rich import box
from seo_bhishma_cli import link_sniper, site_mapper, index_spy, sitemap_generator, keyword_sorcerer, gsc_probe, redirection_genius, domain_insight, hannibal
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR, CLI_MESSAGE

console = Console()

@click.group(invoke_without_command=True)
@click.version_option(version=f"v{CLI_VERSION}", prog_name=CLI_NAME)
@click.option("--word", is_flag=True, show_default=True, default=False, help="save the trees!")
@click.pass_context
def cli(ctx, word):
    if word:
        console.print(Panel(CLI_MESSAGE, title="Message to World", subtitle="Swami Vivekananda", subtitle_align="right", border_style="green"))
        exit()
        
    try:
        if ctx.invoked_subcommand is None:
            ctx.invoke(intro)
            ctx.invoke(menu)
    except Exception as e:
        console.print(f"[bold red][-] An error occurred: {e}[/bold red]")

@click.command()
@click.pass_context
def intro(ctx):
    """SEO Bhishma intro"""
    try:
        ascii_art = text2art(CLI_NAME, font='small')
        console.print(f"[bold bright_cyan]{ascii_art}[/bold bright_cyan]")
        console.print(f"[bold green]Welcome to {CLI_NAME}![/bold green]")
        console.print(f"[green][+] Version: {CLI_VERSION}[/green]")
        console.print(f"[green][+] Author: {CLI_AUTHOR}\n[/green]")
        console.print(f"[dim white]This tool is my way of giving back to the community.[/dim white]")
        console.print(f"[dim white]Support: [underline]https://buymeacoffee.com/rathorehitendra[/underline][/dim white]\n")
    except Exception as e:
        console.print(f"[bold red][-] An error occurred: {e}[/bold red]")

@click.command()
@click.pass_context
def menu(ctx):
    """Main Menu of SEO Bhishma"""
    while True:
        try:
            table = Table(show_header=False, box=box.ROUNDED, style="blue")
            table.add_row("[bold magenta]1.[/bold magenta]", "[yellow]GSC Probe[/yellow]")
            table.add_row("[bold magenta]2.[/bold magenta]", "[yellow]Domain Insights[/yellow]")
            table.add_row("[bold magenta]3.[/bold magenta]", "[yellow]Keyword Sorcerer[/yellow]")
            table.add_row("[bold magenta]4.[/bold magenta]", "[yellow]Hannibal[/yellow]")
            table.add_row("[bold magenta]5.[/bold magenta]", "[yellow]IndexSpy[/yellow]")
            table.add_row("[bold magenta]6.[/bold magenta]", "[yellow]Redirection Genius[/yellow]")
            table.add_row("[bold magenta]7.[/bold magenta]", "[yellow]LinkSniper[/yellow]")
            table.add_row("[bold magenta]8.[/bold magenta]", "[yellow]SiteMapper[/yellow]")            
            table.add_row("[bold magenta]9.[/bold magenta]", "[yellow]Sitemap Generator[/yellow]")       
            table.add_row("[bold red]0.[/bold red]", "[red]Exit[/red]")
            
            console.print(table)

            choice = Prompt.ask("[bold cyan]Enter your choice[/bold cyan]", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"])

            if choice == "1":
                ctx.invoke(gsc_probe)
            elif choice == "2":
                ctx.invoke(domain_insight)
            elif choice == "3":
                ctx.invoke(keyword_sorcerer)
            elif choice == "4":
                ctx.invoke(hannibal)
            elif choice == "5":
                ctx.invoke(index_spy)
            elif choice == "6":
                ctx.invoke(redirection_genius)
            elif choice == "7":
                ctx.invoke(link_sniper)
            elif choice == "8":
                ctx.invoke(site_mapper)
            elif choice == "9":
                ctx.invoke(sitemap_generator)
            elif choice == "0":
                console.print(f"[bold red]Exiting {CLI_NAME}. Goodbye![/bold red]")
                break
        except Exception as e:
            console.print(f"[bold red][-] An error occurred: {e}[/bold red]")

cli.add_command(menu)
cli.add_command(intro)
cli.add_command(link_sniper)
cli.add_command(site_mapper)
cli.add_command(index_spy)
cli.add_command(sitemap_generator)
cli.add_command(keyword_sorcerer)
cli.add_command(gsc_probe)
cli.add_command(redirection_genius)
cli.add_command(domain_insight)
cli.add_command(hannibal)

if __name__ == "__main__":
    cli()

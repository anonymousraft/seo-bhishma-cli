from seo_bhishma_cli.common import *
from art import text2art
from rich.table import Table
from rich import box
from seo_bhishma_cli import link_sniper, site_mapper, index_spy, sitemap_generator, keyword_sorcerer, gsc_probe, redirection_genius, domain_insight, hannibal

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
        ascii_art = text2art(CLI_NAME, font='tarty2')
        console.print(f"[bold green]{ascii_art}[/bold green]")
        console.print(f"[italic green]v{CLI_VERSION}, {CLI_AUTHOR}\n[/italic green]")
        console.print(f"[dim white]Giving back to the community.[/dim white]")
        console.print(f"[dim white]Support: [underline]https://t.ly/hitendra[/underline][/dim white]\n")
    except Exception as e:
        console.print(f"[bold red][-] An error occurred: {e}[/bold red]")

@click.command()
@click.pass_context
def menu(ctx):
    """Main Menu of SEO Bhishma"""
    while True:
        try:
            table = Table(show_header=False, box=box.ROUNDED, style="dim white")
            table.add_row("[bold white]1.[/bold white]", "[white]GSC Probe[/white]")
            table.add_row("[bold white]2.[/bold white]", "[white]Domain Insights[/white]")
            table.add_row("[bold white]3.[/bold white]", "[white]Keyword Sorcerer[/white]")
            table.add_row("[bold white]4.[/bold white]", "[white]Hannibal[/white]")
            table.add_row("[bold white]5.[/bold white]", "[white]IndexSpy[/white]")
            table.add_row("[bold white]6.[/bold white]", "[white]Redirection Genius[/white]")
            table.add_row("[bold white]7.[/bold white]", "[white]LinkSniper[/white]")
            table.add_row("[bold white]8.[/bold white]", "[white]SiteMapper[/white]")            
            table.add_row("[bold white]9.[/bold white]", "[white]Sitemap Generator[/white]")       
            table.add_row("[bold red]0.[/bold red]", "[red]Exit[/red]")
            
            console.print(table)

            choice = Prompt.ask("[bold white]Enter your choice[/bold white]", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"])

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

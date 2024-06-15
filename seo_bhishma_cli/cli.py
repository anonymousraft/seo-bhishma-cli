import click
from art import text2art
from seo_bhishma_cli import link_sniper, site_mapper, index_spy
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR

@click.group(invoke_without_command=True)
@click.version_option(version=CLI_VERSION, prog_name=CLI_NAME)
@click.pass_context
def cli(ctx):
    ascii_art = text2art(CLI_NAME)
    click.echo("\n" + "="*50 + "\n")
    click.echo(click.style(ascii_art, fg="cyan", bold=True))
    click.echo(click.style(f"Welcome to {CLI_NAME}!", fg="green", bold=True))
    click.echo(click.style(f"Version: {CLI_VERSION}", fg="green"))
    click.echo(click.style(f"Author: {CLI_AUTHOR}\n", fg="green"))

    if ctx.invoked_subcommand is None:
        ctx.invoke(menu)

@click.command()
@click.pass_context
def menu(ctx):
    while True:
        click.echo(click.style("1. LinkSniper - Check Backlinks", fg="yellow"))
        click.echo(click.style("2. SiteMapper - Download Sitemap", fg="yellow"))
        click.echo(click.style("3. IndexSpy - Bulk Indexing Checker", fg="yellow"))
        click.echo(click.style("4. Exit", fg="red", bold=True))
        
        choice = click.prompt(click.style("Enter your choice", fg="cyan", bold=True), type=int)
        
        if choice == 1:
            ctx.invoke(link_sniper)
        elif choice == 2:
            ctx.invoke(site_mapper)
        elif choice == 3:
            ctx.invoke(index_spy)
        elif choice == 4:
            click.echo(click.style(f"Exiting {CLI_NAME}. Goodbye!", fg="red", bold=True))
            break
        else:
            click.echo(click.style("Invalid choice. Please select a valid option.", fg="red"))

        click.echo("\n" + "="*50 + "\n")

cli.add_command(menu)
cli.add_command(link_sniper)
cli.add_command(site_mapper)
cli.add_command(index_spy)

if __name__ == "__main__":
    cli()

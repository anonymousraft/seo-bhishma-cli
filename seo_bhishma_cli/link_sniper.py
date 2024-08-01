import requests
from bs4 import BeautifulSoup
import pandas as pd
import click
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from datetime import datetime
from rich.panel import Panel
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR

console = Console()

def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=0.3,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def check_backlink(backlink_url, target_url, expected_anchor=None):
    try:
        response = requests_retry_session().get(backlink_url, timeout=10)
        if response.status_code != 200:
            return "Not Live", "N/A", "No", None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=target_url)
        if not links:
            return "Not Found", "N/A", "No", None
        
        actual_anchor_texts = [link.text for link in links]
        if expected_anchor:
            expected_anchor = str(expected_anchor) if not pd.isna(expected_anchor) else ""
            for link in links:
                if expected_anchor in link.text:
                    return "Live", "Present", "Yes", ', '.join(actual_anchor_texts)
            return "Live", "Missing", "Yes", ', '.join(actual_anchor_texts)
        
        return "Live", "Present", "Yes", ', '.join(actual_anchor_texts) if links else None
    except requests.RequestException as e:
        return "Error", str(e), "No", None
    except Exception as e:
        return "Error", f"[-] Unexpected error: {str(e)}", "No", None

def read_input_file(file_path):
    try:
        if file_path.endswith('.csv'):
            return pd.read_csv(file_path)
        elif file_path.endswith('.json'):
            return pd.read_json(file_path)
        else:
            raise ValueError("[-] Unsupported file format. Use CSV or JSON.")
    except Exception as e:
        console.print(f"[red][-] Error reading input file: {e}[/red]")
        raise

def generate_report(results, output_file):
    try:
        df = pd.DataFrame(results)
        df.to_csv(output_file, index=False, encoding='utf-8')
        console.print(f"[green][+] Report generated: {output_file}[/green]")
    except Exception as e:
        console.print(f"[red][-] Error generating report: {e}[/red]")

def process_url(row):
    backlink_url = row['backlink_url']
    target_url = row['target_url']
    expected_anchor = row.get('expected_anchor', "")
    status, anchor_status, link_exists, actual_anchor_text = check_backlink(backlink_url, target_url, expected_anchor)
    return {
        'backlink_url': backlink_url,
        'target_url': target_url,
        'status': status,
        'anchor_status': anchor_status,
        'link_exists': link_exists,
        'actual_anchor_text': actual_anchor_text
    }

@click.command()
@click.pass_context
def link_sniper(ctx):
    """Check if backlinks are live and verify anchor texts."""
    while True:
        console.print(Panel("Link Sniper\nCheck bulk backlinks to determine if they are live or not.", title="Link Sniper", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))
        console.print("[cyan]1. Check a single URL[/cyan]")
        console.print("[cyan]2. Check URLs from a file[/cyan]")
        console.print("[red bold]3. Exit[/red bold]")
        choice = click.prompt("Enter your choice", type=int)

        if choice == 1:
            backlink_url = click.prompt("Enter the backlink URL")
            target_url = click.prompt("Enter the target URL")
            expected_anchor = click.prompt("Enter the expected anchor text (optional)", default="", show_default=False)
            status, anchor_status, link_exists, actual_anchor_text = check_backlink(backlink_url, target_url, expected_anchor)
            
            console.print(f"[cyan][+] Backlink URL: {backlink_url}[/cyan]")
            console.print(f"[cyan][+] Target URL: {target_url}[/cyan]")

            # Set different colors for status
            if status == "Live":
                console.print(f"[green][+] Status: {status}[/green]")
            elif status == "Not Live":
                console.print(f"[red][+] Status: {status}[/red]")
            else:
                console.print(f"[yellow][+] Status: {status}[/yellow]")

            # Set different colors for anchor status
            if anchor_status == "Present":
                console.print(f"[green][+] Anchor Text Status: {anchor_status}[/green]")
                console.print(f"[green][+] Actual Anchor Text: {actual_anchor_text}[/green]")
            elif anchor_status == "Missing":
                console.print(f"[red][+] Anchor Text Status: {anchor_status}[/red]")
            else:
                console.print(f"[yellow][+] Anchor Text Status: {anchor_status}[/yellow]")

            console.print(f"[cyan][+] Link Exists: {link_exists}[/cyan]")

        elif choice == 2:
            input_file = click.prompt("Enter the path to the input file (CSV/JSON)", type=click.Path(exists=True))
            now = datetime.now().strftime("%Y%m%d%H%M%S")
            default_output_file = f"backlink_report_{now}.csv"
            output_file = click.prompt("Enter the path to the output CSV file", default=default_output_file, show_default=True, type=click.Path())
            data = read_input_file(input_file)
            results = []

            console.print("[green bold][+] Processing URLs...[/green bold]")

            with ThreadPoolExecutor(max_workers=10) as executor:
                with Progress(
                    SpinnerColumn(),
                    BarColumn(bar_width=None),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                    transient=True
                ) as progress:
                    task = progress.add_task("[+] Checking URLs...", total=len(data))
                    futures = [executor.submit(process_url, row) for index, row in data.iterrows()]
                    for future in futures:
                        results.append(future.result())
                        progress.update(task, advance=1)

            generate_report(results, output_file)
            found_count = sum(1 for result in results if result['link_exists'] == "Yes")
            console.print(f"[green bold][+] Summary: {found_count} target URLs found in the backlinks out of {len(results)} processed.[/green bold]")

        elif choice == 3:
            console.print("[red bold]Exiting LinkSniper. Goodbye![/red bold]")
            break
        else:
            console.print("[red][-] Invalid choice. Please select a valid option.[/red]")

        console.print("="*50)

if __name__ == "__main__":
    link_sniper()

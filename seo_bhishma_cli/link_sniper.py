import requests
from bs4 import BeautifulSoup
import pandas as pd
import click
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

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
        backoff_factor=backoff_factor,
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

def read_input_file(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    elif file_path.endswith('.json'):
        return pd.read_json(file_path)
    else:
        raise ValueError("Unsupported file format. Use CSV or JSON.")

def generate_report(results, output_file):
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    click.echo(click.style(f"Report generated: {output_file}", fg="green", bold=True))

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
        click.echo("\n" + "="*50)
        click.echo(click.style("LinkSniper - Check Backlinks", fg="yellow", bold=True))
        click.echo(click.style("1. Check a single URL", fg="cyan"))
        click.echo(click.style("2. Check URLs from a file", fg="cyan"))
        click.echo(click.style("3. Exit", fg="red", bold=True))
        choice = click.prompt(click.style("Enter your choice", fg="cyan", bold=True), type=int)

        if choice == 1:
            backlink_url = click.prompt(click.style("Enter the backlink URL", fg="cyan"))
            target_url = click.prompt(click.style("Enter the target URL", fg="cyan"))
            expected_anchor = click.prompt(click.style("Enter the expected anchor text (optional)", fg="cyan"), default="", show_default=False)
            status, anchor_status, link_exists, actual_anchor_text = check_backlink(backlink_url, target_url, expected_anchor)
            
            click.echo(click.style(f"Backlink URL: {backlink_url}", fg="cyan"))
            click.echo(click.style(f"Target URL: {target_url}", fg="cyan"))

            # Set different colors for status
            if status == "Live":
                click.echo(click.style(f"Status: {status}", fg="green"))
            elif status == "Not Live":
                click.echo(click.style(f"Status: {status}", fg="red"))
            else:
                click.echo(click.style(f"Status: {status}", fg="yellow"))

            # Set different colors for anchor status
            if anchor_status == "Present":
                click.echo(click.style(f"Anchor Text Status: {anchor_status}", fg="green"))
                click.echo(click.style(f"Actual Anchor Text: {actual_anchor_text}", fg="green"))
            elif anchor_status == "Missing":
                click.echo(click.style(f"Anchor Text Status: {anchor_status}", fg="red"))
            else:
                click.echo(click.style(f"Anchor Text Status: {anchor_status}", fg="yellow"))

            click.echo(click.style(f"Link Exists: {link_exists}", fg="cyan"))

        elif choice == 2:
            input_file = click.prompt(click.style("Enter the path to the input file (CSV/JSON)", fg="cyan"), type=click.Path(exists=True))
            output_file = click.prompt(click.style("Enter the path to the output CSV file", fg="cyan"), type=click.Path())
            data = read_input_file(input_file)
            results = []
            click.echo(click.style("Processing URLs...", fg="green", bold=True))

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(process_url, row) for index, row in data.iterrows()]
                for future in tqdm(futures, desc="Checking URLs", total=len(futures), colour="cyan"):
                    results.append(future.result())

            generate_report(results, output_file)
            found_count = sum(1 for result in results if result['link_exists'] == "Yes")
            click.echo(click.style(f"Summary: {found_count} target URLs found in the backlinks out of {len(results)} processed.", fg="green", bold=True))

        elif choice == 3:
            click.echo(click.style("Exiting LinkSniper. Goodbye!", fg="red", bold=True))
            break
        else:
            click.echo(click.style("Invalid choice. Please select a valid option.", fg="red"))

        click.echo("="*50)

if __name__ == "__main__":
    link_sniper()

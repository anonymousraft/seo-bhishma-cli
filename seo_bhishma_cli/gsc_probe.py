import os
import pickle
import csv
import requests
import time
import click
import pandas as pd
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from rich.console import Console
from rich.panel import Panel
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR
from rich.progress import Progress, BarColumn, TimeRemainingColumn
from rich.logging import RichHandler
import signal
import logging
import json
from datetime import datetime, timedelta, timezone

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s', handlers=[RichHandler()])
logger = logging.getLogger("rich")

console = Console()

SCOPES = [
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/webmasters'
]
progress = None
output_file = None

def signal_handler(sig, frame):
    console.log("[bold yellow][/] Process interrupted! Progress has been saved.[/bold yellow]")
    if progress:
        save_progress(progress['data'], output_file)
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def authenticate_gsc(creds_path=None):
    creds = None
    token_path = 'token.pickle'
    
    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path:
                creds_path = click.prompt(click.style("Enter the path to the credentials JSON file", fg="yellow"))
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
    
    service = build('searchconsole', 'v1', credentials=creds)
    return service

def save_progress(data, output_file):
    temp_file = output_file + ".temp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f)

def load_progress(output_file):
    temp_file = output_file + ".temp"
    if os.path.exists(temp_file):
        with open(temp_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def fetch_site_list(service):
    try:
        site_list = service.sites().list().execute()
        return site_list
    except Exception as e:
        console.print(f"[bold red][-] An error occurred: {e}[/bold red]")
        return None

def save_gsc_data(site_url, data, dimensions, data_type):
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"gsc_data/{site_url.replace('https://', '').replace('/', '_')}_{timestamp}_{'_'.join(dimensions)}_{data_type}.csv"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    if data_type == 'search_analytics':
        if 'rows' in data and data['rows']:
            keys = dimensions + [col for col in data['rows'][0].keys() if col != 'keys']
            with open(filename, 'w', newline='', encoding='utf-8') as output_file:
                dict_writer = csv.DictWriter(output_file, fieldnames=keys)
                dict_writer.writeheader()
                for row in data['rows']:
                    if 'keys' in row:
                        row.update({dimension: value for dimension, value in zip(dimensions, row.pop('keys'))})
                    dict_writer.writerow(row)
    elif data_type == 'sitemaps':
        with open(filename, 'w', newline='', encoding='utf-8') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=data[0].keys())
            dict_writer.writeheader()
            dict_writer.writerows(data)
    else:
        keys = data['rows'][0].keys() if 'rows' in data else data.keys()
        with open(filename, 'w', newline='', encoding='utf-8') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            if 'rows' in data:
                dict_writer.writerows(data['rows'])
            else:
                dict_writer.writerow(data)
    
    return filename

def fetch_search_analytics(service, site_url, start_date, end_date, dimensions, row_limit, filters=None, search_type='web'):
    data = []
    request = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': dimensions,
        'rowLimit': 5000,
        'searchType': search_type
    }
    if filters:
        request['dimensionFilterGroups'] = [{'filters': filters}]

    total_rows_fetched = 0

    with Progress(BarColumn(), "[progress.percentage]{task.percentage:>3.1f}%", TimeRemainingColumn(), console=console) as progress_bar:
        task = progress_bar.add_task("[cyan][+] Fetching GSC data...", total=row_limit or 1000)
        
        while True:
            try:
                response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
                rows = response.get('rows', [])
                if not rows:
                    break
                data.extend(rows)
                total_rows_fetched += len(rows)
                # console.log(f"[green][+] {total_rows_fetched} rows fetched so far...[/green]")
                progress_bar.update(task, advance=len(rows))
                request['startRow'] = len(data)  # Continue fetching rows
                time.sleep(1)  # To respect rate limits
                if row_limit and total_rows_fetched >= row_limit:
                    break
            except Exception as e:
                console.print(f"[bold red][-] An error occurred: {e}[/bold red]")
                break

    if not data:
        console.print("[red][-] No data fetched. Please check your query parameters and try again.[/red]")
    else:
        console.log(f"[green][+] {total_rows_fetched} rows fetched.[/green]")
        save_gsc_data(site_url, {'rows': data}, dimensions, 'search_analytics')
    return data

def fetch_sitemaps(service, site_url):
    try:
        sitemaps = service.sitemaps().list(siteUrl=site_url).execute()
        if 'sitemap' in sitemaps:
            sitemaps_list = sitemaps['sitemap']
            sitemaps_data = [{'path': sitemap['path'], 'lastDownloaded': sitemap.get('lastDownloaded', ''), 'type': sitemap.get('type', '')} for sitemap in sitemaps_list]
            save_gsc_data(site_url, sitemaps_data, ['sitemap'], 'sitemaps')
            return sitemaps_data
        else:
            console.print("[red][-] No sitemaps found for this site.[/red]")
            return []
    except Exception as e:
        console.print(f"[bold red][-] An error occurred: {e}[/bold red]")
        return None

def fetch_url_inspection(service, site_url, url_list):
    try:
        batch_response = []
        with Progress(BarColumn(), "[progress.percentage]{task.percentage:>3.1f}%", TimeRemainingColumn(), console=console) as progress_bar:
            task = progress_bar.add_task("[cyan][+] Inspecting URLs...", total=len(url_list))
            for url in url_list:
                inspection_result = service.urlInspection().index().inspect(body={'inspectionUrl': url, 'siteUrl': site_url}).execute()
                batch_response.append(inspection_result)
                progress_bar.update(task, advance=1)
                time.sleep(1)  # To respect rate limits
        return batch_response
    except Exception as e:
        console.print(f"[bold red][-] An error occurred: {e}[/bold red]")
        return None

def get_available_dates(service, site_url):
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body={'startDate': '2000-01-01', 'endDate': '2100-01-01', 'dimensions': ['date'], 'rowLimit': 1}).execute()
        if 'rows' in response:
            start_date = response['rows'][0]['keys'][0]
            end_date = response['rows'][-1]['keys'][0]
            return start_date, end_date
        else:
            return None, None
    except Exception as e:
        console.print(f"[bold red][-] An error occurred while fetching available dates: {e}[/bold red]")
        return None, None

@click.command()
@click.pass_context
def gsc_probe(ctx):
    """Google Search Console Data Extraction Tool!"""
    creds_path = None
    while True:
        console.print(Panel("Welcome to GSC Probe!\nThis tool helps you extract various types of data from your Google Search Console account.", title="GSC Probe", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))

        service = authenticate_gsc(creds_path)
        
        site_list = fetch_site_list(service)
        if not site_list:
            console.print("[bold red][-] Unable to fetch site list. Please check your credentials and try again.[/bold red]")
            creds_path = None  # Prompt for credentials path again
            continue

        console.print("[green][+] Available sites in your GSC account:[/green]")
        site_entries = site_list.get('siteEntry', [])
        for index, site in enumerate(site_entries, start=1):
            console.print(f"[cyan]{index}.[/cyan] {site['siteUrl']}")

        site_choice = click.prompt(click.style("Enter the number of the site you want to select (or type 'exit' to quit)", fg="magenta"))
        if site_choice.lower() == 'exit':
            console.print("[bold red]Thank you for using GSC Probe! Goodbye![/bold red]")
            break
        
        try:
            site_index = int(site_choice) - 1
            if site_index < 0 or site_index >= len(site_entries):
                raise ValueError("[-] Invalid site number.")
            site_url = site_entries[site_index]['siteUrl']
        except ValueError as ve:
            console.print(f"[red][-] {ve}. Please enter a valid number.")
            continue

        start_date, _ = get_available_dates(service, site_url)
        end_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime('%Y-%m-%d')

        if not start_date or not end_date:
            console.print("[bold red][-] Unable to fetch available dates. Please check your site and try again.[/bold red]")
            continue
        
        available_dimensions = "date,query,page,country,device,searchAppearance"

        while True:
            console.print("\n[yellow]Select the type of data to extract:[/yellow]\n")
            data_type = click.prompt(click.style("1. Search Analytics\n2. Sitemaps\n3. URL Inspection\n4. Exit\nEnter the number of your choice", fg="magenta"), type=int)

            if data_type == 1:
                start_date_input = click.prompt(click.style("Enter the start date (YYYY-MM-DD)", fg="magenta"), default=start_date, show_default=True)
                end_date_input = click.prompt(click.style("Enter the end date (YYYY-MM-DD)", fg="magenta"), default=end_date, show_default=True)
                dimensions = click.prompt(click.style(f"Enter the dimensions (comma-separated, available: {available_dimensions})", fg="magenta"), default="date", show_default=True).split(',')
                search_type = click.prompt(click.style("Enter the search type (web/image/video/news)", fg="magenta"), default="web")
                row_limit_input = click.prompt(click.style("Enter the row limit (leave blank for default: 25000, type 'max' for maximum available)", fg="magenta"), default="25000", show_default=True)
                
                if row_limit_input.lower() == 'max':
                    row_limit = None  # Let the API fetch maximum available rows
                else:
                    try:
                        row_limit = int(row_limit_input)
                    except ValueError:
                        console.print("[red][-] Invalid row limit. Please enter a valid number or 'max'.[/red]")
                        continue

                filters = []
                add_filter = click.prompt(click.style("Do you want to add any filters? (yes/no)", fg="magenta"), default="no", show_default=True)
                if add_filter.lower() == 'yes':
                    for dimension in dimensions:
                        apply_filter = click.prompt(click.style(f"Do you want to apply filter for dimension '{dimension}'? (yes/no)", fg="magenta"), default="yes", show_default=True)
                        if apply_filter.lower() == 'yes':
                            filter_operator = click.prompt(click.style("Enter the filter operator (e.g., equals, contains, notContains, includingRegex, excludingRegex)", fg="magenta"), default="equals")
                            filter_expression = click.prompt(click.style("Enter the filter expression", fg="magenta"))
                            if filter_operator in ["includingRegex", "excludingRegex"]:
                                if filter_operator == "includingRegex":
                                    filter_operator = "includingRegex"
                                else:
                                    filter_operator = "excludingRegex"
                            filters.append({
                                'dimension': dimension,
                                'operator': filter_operator,
                                'expression': filter_expression
                            })

                device_filter = click.prompt(click.style("Enter device filter (e.g., MOBILE, DESKTOP, TABLET) or leave blank for no filter", fg="magenta"), default="", show_default=True)
                country_filter = click.prompt(click.style("Enter country filter (ISO 3166-1 alpha-2 code, eg. IND for india) or leave blank for no filter", fg="magenta"), default="", show_default=True)

                if device_filter:
                    filters.append({
                        'dimension': 'device',
                        'operator': 'equals',
                        'expression': device_filter
                    })

                if country_filter:
                    filters.append({
                        'dimension': 'country',
                        'operator': 'equals',
                        'expression': country_filter
                    })

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                default_filename = f"gsc_data/gsc_output_{timestamp}.csv"
                output_file = click.prompt(click.style(f"Enter the path to the output CSV file (leave blank for default: {default_filename})", fg="magenta"), default=default_filename, show_default=True)
                
                data = load_progress(output_file)
                if data:
                    console.log("[yellow][+] Resuming from previous progress...[/yellow]")
                else:
                    console.log("[green][+] Starting new GSC data extraction...[/green]")
                
                console.log("[green][+] Fetching GSC data...[/green]")
                new_data = fetch_search_analytics(service, site_url, start_date_input, end_date_input, dimensions, row_limit, filters)
                data.extend(new_data)
                
                if not data:
                    console.print("[red][-] No data fetched. Please check your query parameters and try again.[/red]")
                else:
                    df = pd.DataFrame(data)
                    df.to_csv(output_file, index=False, encoding='utf-8')
                    if os.path.exists(output_file + ".temp"):
                        os.remove(output_file + ".temp")
                    console.log(f"[green][+] GSC data saved to {output_file}[/green]")
            
            elif data_type == 2:
                console.log("[green][+] Fetching sitemaps data...[/green]")
                sitemaps = fetch_sitemaps(service, site_url)
                if sitemaps:
                    num_sitemaps = len(sitemaps)
                    console.log(f"[green][+] Sitemaps data saved. Number of sitemaps saved: {num_sitemaps}[/green]")
            
            elif data_type == 3:
                console.print("\n[yellow]URL Inspection Options:[/yellow]\n")
                url_inspect_type = click.prompt(click.style("1. Single URL\n2. Batch Process\nEnter the number of your choice", fg="magenta"), type=int)

                if url_inspect_type == 1:
                    url = click.prompt(click.style("Enter the URL to inspect", fg="magenta"))
                    console.log("[green][+] Fetching URL inspection data...[/green]")
                    inspection_result = fetch_url_inspection(service, site_url, [url])
                    if inspection_result:
                        console.print(inspection_result)

                elif url_inspect_type == 2:
                    csv_file_path = click.prompt(click.style("Enter the path to the CSV file containing URLs", fg="magenta"))
                    try:
                        df = pd.read_csv(csv_file_path, encoding='utf-8')
                        urls = df['urls'].tolist()
                        console.log("[green][+] Fetching URL inspection data...[/green]")
                        inspection_results = fetch_url_inspection(service, site_url, urls)
                        if inspection_results:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            output_filename = f"gsc_data/url_inspection_output_{timestamp}.csv"
                            output_file = click.prompt(click.style(f"Enter the path to the output CSV file (leave blank for default: {output_filename})", fg="magenta"), default=output_filename, show_default=True)
                            pd.DataFrame(inspection_results).to_csv(output_file, index=False, encoding='utf-8')
                            console.log(f"[green][+] URL inspection data saved to {output_file}[/green]")
                    except Exception as e:
                        console.print(f"[bold red][-] An error occurred while reading the CSV file: {e}[/bold red]")

            elif data_type == 4:
                break

            else:
                console.print("[red][-] Invalid choice! Please select a valid option.[/red]")

if __name__ == "__main__":
    gsc_probe()

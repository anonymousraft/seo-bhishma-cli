import requests
import pandas as pd
import xml.etree.ElementTree as ET
import gzip
import click
from urllib.parse import urlparse
import logging
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, BarColumn, TimeRemainingColumn
from rich.logging import RichHandler
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal
from rich.panel import Panel
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s', handlers=[RichHandler()])
logger = logging.getLogger("rich")

console = Console()

NAMESPACE = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
progress = None
output_file = None

def extract_domain(url):
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc if parsed_url.netloc else parsed_url.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception as e:
        console.log(f"[bold red]Error extracting domain from URL: {e}[/bold red]")
        return None

def signal_handler(sig, frame):
    console.log("[bold yellow][+] Process interrupted! Progress has been saved.[/bold yellow]")
    if progress:
        save_progress(progress['urls'], output_file)
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def download_sitemap(url):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        if url.endswith('.gz'):
            with gzip.GzipFile(fileobj=response.raw) as f:
                return ET.parse(f).getroot()
        else:
            return ET.fromstring(response.content)
    except requests.RequestException as e:
        console.log(f"[bold red][-] Error downloading sitemap: {e}[/bold red]")
        return None
    except ET.ParseError as e:
        console.log(f"[bold red][-] Error parsing sitemap: {e}[/bold red]")
        return None

def save_progress(urls, output_file):
    temp_file = output_file + ".temp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(urls, f)

def load_progress(output_file):
    temp_file = output_file + ".temp"
    if os.path.exists(temp_file):
        with open(temp_file, 'r') as f:
            return json.load(f)
    return []

def parse_url_element(url_elem, sitemap_name):
    try:
        loc = url_elem.find('ns:loc', NAMESPACE).text
        lastmod = url_elem.find('ns:lastmod', NAMESPACE).text if url_elem.find('ns:lastmod', NAMESPACE) is not None else ''
        changefreq = url_elem.find('ns:changefreq', NAMESPACE).text if url_elem.find('ns:changefreq', NAMESPACE) is not None else ''
        priority = url_elem.find('ns:priority', NAMESPACE).text if url_elem.find('ns:priority', NAMESPACE) is not None else ''

        images = url_elem.findall('ns:image', NAMESPACE)
        image_data = []
        for image in images:
            image_loc = image.find('ns:loc', NAMESPACE).text
            image_caption = image.find('ns:caption', NAMESPACE).text if image.find('ns:caption', NAMESPACE) is not None else ''
            image_data.append({'loc': image_loc, 'caption': image_caption})

        videos = url_elem.findall('ns:video', NAMESPACE)
        video_data = []
        for video in videos:
            video_loc = video.find('ns:content_loc', NAMESPACE).text if video.find('ns:content_loc', NAMESPACE) is not None else ''
            video_title = video.find('ns:title', NAMESPACE).text if video.find('ns:title', NAMESPACE) is not None else ''
            video_data.append({'loc': video_loc, 'title': video_title})

        news = url_elem.findall('ns:news', NAMESPACE)
        news_data = []
        for news_item in news:
            news_publication_date = news_item.find('ns:publication_date', NAMESPACE).text if news_item.find('ns:publication_date', NAMESPACE) is not None else ''
            news_title = news_item.find('ns:title', NAMESPACE).text if news_item.find('ns:title', NAMESPACE) is not None else ''
            news_data.append({'publication_date': news_publication_date, 'title': news_title})

        return {
            'sitemap_name': sitemap_name,
            'loc': loc,
            'lastmod': lastmod,
            'changefreq': changefreq,
            'priority': priority,
            'images': image_data,
            'videos': video_data,
            'news': news_data
        }
    except Exception as e:
        console.log(f"[bold red][-] Error parsing URL element: {e}[/bold red]")
        return None

def parse_sitemap(root, urls, sitemap_name, level=0, output_file=None):
    sitemaps = root.findall('ns:sitemap', NAMESPACE)
    if sitemaps:
        console.log(f"[blue][+] Found {len(sitemaps)} nested sitemaps. Parsing...[/blue]")
        for i, sitemap in enumerate(sitemaps, start=1):
            loc = sitemap.find('ns:loc', NAMESPACE).text
            console.log(f"[yellow][+] Parsing sitemap {i}/{len(sitemaps)}: {loc}[/yellow]")
            sitemap_root = download_sitemap(loc)
            if sitemap_root:
                parse_sitemap(sitemap_root, urls, loc, level + 1, output_file)
    else:
        url_count = len(root.findall('ns:url', NAMESPACE))
        console.log(f"[blue][+] Parsing {url_count} URLs in sitemap...[/blue]")
        with Progress(BarColumn(), "[progress.percentage]{task.percentage:>3.1f}%", TimeRemainingColumn(), console=console) as progress_bar:
            task = progress_bar.add_task("[cyan][+] Parsing URLs...", total=url_count)
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(parse_url_element, url_elem, sitemap_name): url_elem for url_elem in root.findall('ns:url', NAMESPACE)}
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        urls.append(result)
                        progress_bar.update(task, advance=1)

@click.command()
@click.option('--sitemap-url', default=None, help='URL of the sitemap to download and parse')
@click.option('--output-file', default=None, help='Path to the output CSV file')
def site_mapper(sitemap_url, output_file):
    """Download and parse sitemaps, export URLs to CSV."""
    global progress
    
    try:
        console.print(Panel("Welcome to Sitemapper\nDownload sitemap in CSV file. Support nested & compressed sitemaps", title="Sitemapper", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))        
        if not sitemap_url:
            sitemap_url = click.prompt(click.style("Enter the URL of the sitemap (supports .xml and .gz)", fg="cyan", bold=True))
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        domain_name = extract_domain(sitemap_url)
        default_filename = f"{domain_name}_sitemap_{timestamp}.csv"
        
        if output_file:
            file_path, file_name = os.path.split(output_file)
            file_base, file_extension = os.path.splitext(file_name)
            output_file = os.path.join(file_path, f"{file_base}_{timestamp}{file_extension}")
        else:
            output_file = click.prompt(click.style(f"Enter the path to the output CSV file (leave blank for default: {default_filename})", fg="cyan", bold=True), default=default_filename, show_default=True)
        
        urls = load_progress(output_file)
        if urls:
            console.log("[yellow][+] Resuming from previous progress...[/yellow]")
        else:
            console.log("[green][+] Starting new sitemap parsing...[/green]")
        
        console.log("[green][+] Downloading and parsing sitemap...[/green]")
        root = download_sitemap(sitemap_url)
        if root:
            progress = {'urls': urls}
            parse_sitemap(root, urls, sitemap_url, output_file=output_file)
            df = pd.DataFrame(urls)
            df.to_csv(output_file, index=False, encoding='utf-8')
            if os.path.exists(output_file + ".temp"):
                os.remove(output_file + ".temp")
            console.log(f"[green][+] Sitemap data saved to {output_file}[/green]")
            console.log("\n")
        else:
            console.log("[bold red][-] Failed to process sitemap.[/bold red]")
    except Exception as e:
        console.log(f"[bold red][-] An error occurred: {e}[/bold red]")

if __name__ == "__main__":
    site_mapper()
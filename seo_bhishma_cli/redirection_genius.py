import pandas as pd
import numpy as np
import click
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, BarColumn, TimeRemainingColumn
from rich.logging import RichHandler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from difflib import SequenceMatcher
import spacy
from spacy.cli import download
from urllib.parse import urlparse
import requests
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import signal
from rich.panel import Panel
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR

# Ensure the spaCy model is available
def ensure_spacy_model(model_name):
    try:
        nlp = spacy.load(model_name)
    except OSError:
        print(f"[+] Downloading spaCy model '{model_name}'...")
        download(model_name)
        nlp = spacy.load(model_name)
    return nlp

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s', handlers=[RichHandler()])
logger = logging.getLogger("rich")

console = Console()

# Load spaCy model
nlp = ensure_spacy_model('en_core_web_sm')

# Global variables to handle progress saving
interrupted = False
progress_data = []

# Signal handler for saving progress
def signal_handler(sig, frame):
    global interrupted
    interrupted = True
    console.log("[bold yellow][-] Process interrupted! Progress will be saved.[/bold yellow]")

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Define functions for URL mapping methods
def extract_slug(url):
    parsed_url = urlparse(url)
    return parsed_url.path

def analyze_slug(slug):
    doc = nlp(slug.replace('-', ' '))
    return [token.lemma_ for token in doc if not token.is_stop and not token.is_punct]

def jaccard_similarity(set1, set2):
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    return float(len(intersection)) / len(union)

def sequence_matcher(str1, str2):
    return SequenceMatcher(None, str1, str2).ratio()

def tfidf_similarity(source_slugs, dest_slugs):
    vectorizer = TfidfVectorizer().fit_transform(source_slugs + dest_slugs)
    vectors = vectorizer.toarray()
    source_vectors = vectors[:len(source_slugs)]
    dest_vectors = vectors[len(source_slugs):]
    return cosine_similarity(source_vectors, dest_vectors)

def get_web_content(url, rate_limit):
    try:
        time.sleep(rate_limit)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"[-] Error fetching web content for URL {url}: {e}")
        return None

def save_progress(output_file, data):
    try:
        temp_file = output_file + ".temp"
        df = pd.DataFrame(data, columns=['source', 'destination', 'confidence_score', 'remark'])
        df.to_csv(temp_file, index=False, encoding='utf-8')
        console.log(f"[bold yellow][+] Progress saved to {temp_file}[/bold yellow]")
    except Exception as e:
        console.log(f"[bold red][-] Failed to save progress: {e}[/bold red]")

def map_urls(source_urls, dest_urls, use_web_content_check, rate_limit, output_file):
    global interrupted, progress_data
    results = []
    error_count = 0

    try:
        source_slugs = [extract_slug(url) for url in source_urls]
        dest_slugs = [extract_slug(url) for url in dest_urls]

        source_lemmas = [' '.join(analyze_slug(slug)) for slug in source_slugs]
        dest_lemmas = [' '.join(analyze_slug(slug)) for slug in dest_slugs]

        # TF-IDF similarity
        tfidf_sim = tfidf_similarity(source_lemmas, dest_lemmas)
    except Exception as e:
        console.log(f"[bold red][-] Error processing URL slugs or lemmas: {e}[/bold red]")
        return []

    with Progress(BarColumn(), "[progress.percentage]{task.percentage:>3.1f}%", TimeRemainingColumn(), console=console) as progress:
        task = progress.add_task("[cyan][+] Mapping URLs...", total=len(source_urls))

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(process_url_mapping, i, source_url, dest_urls, tfidf_sim[i], use_web_content_check, rate_limit): source_url for i, source_url in enumerate(source_urls)}
            
            for future in as_completed(future_to_url):
                if interrupted:
                    save_progress(output_file, progress_data)
                    break

                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        progress_data.append(result)
                    progress.update(task, advance=1)
                    if result and result[3] == 'Error':
                        error_count += 1
                        if error_count > 5:
                            console.log("[bold red][-] Too many errors in fetching web content. Skipping URL content check and continuing with normal process.[/bold red]")
                            use_web_content_check = False
                except Exception as e:
                    console.log(f"[bold red][-] Error processing URL mapping: {e}[/bold red]")

    return results

def process_url_mapping(i, source_url, dest_urls, tfidf_scores, use_web_content_check, rate_limit):
    try:
        best_match_idx = np.argmax(tfidf_scores)
        best_match_score = tfidf_scores[best_match_idx]
        remark = ''

        if use_web_content_check and best_match_score < 0.6:
            source_content = get_web_content(source_url, rate_limit)
            dest_content = get_web_content(dest_urls[best_match_idx], rate_limit)
            if source_content and dest_content:
                source_doc = nlp(source_content)
                dest_doc = nlp(dest_content)
                best_match_score = cosine_similarity(
                    [source_doc.vector], 
                    [dest_doc.vector]
                )[0][0]
                remark = 'Check manually' if best_match_score < 0.6 else ''
            else:
                remark = 'Error'
        else:
            remark = 'Check manually' if best_match_score < 0.6 else ''
        
        return (source_url, dest_urls[best_match_idx], best_match_score, remark)
    except Exception as e:
        logger.error(f"[-] Error in processing URL mapping for {source_url}: {e}")
        return (source_url, '', 0, 'Error')

def start_redirection():
    input_file = click.prompt(click.style("Enter the path to the input CSV file", fg="cyan", bold=True))
    if not os.path.isfile(input_file):
        console.print("[bold red][-] Input file not found. Please check the file path and try again.[/bold red]")
        return
    try:
        df = pd.read_csv(input_file)
        if df.empty:
            console.print("[bold red][-] Input file is empty. Please provide a valid CSV file.[/bold red]")
            return
        if 'source' not in df.columns or 'destination' not in df.columns:
            console.print("[bold red][-] Input file must contain 'source' and 'destination' columns.[/bold red]")
            return
    except pd.errors.EmptyDataError:
        console.print("[bold red][-] Input file is empty. Please provide a valid CSV file.[/bold red]")
        return
    except Exception as e:
        console.print(f"[bold red][-] An unexpected error occurred while reading the input file: {e}[/bold red]")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = click.prompt(click.style(f"Enter the path to the output CSV file (leave blank for default: url_mapping_output_{timestamp}.csv)", fg="cyan", bold=True), default=f"url_mapping_output_{timestamp}.csv")
    use_web_content_check = click.confirm(click.style("Do you want to use web content check for more accuracy?", fg="cyan", bold=True))

    rate_limit = 0
    if use_web_content_check:
        rate_limit = click.prompt(click.style("Enter the rate limit in seconds between requests (e.g., 1 for 1 second):", fg="cyan", bold=True), type=float)

    source_urls = df['source'].tolist()
    dest_urls = df['destination'].tolist()
    
    console.log("[green][+] Starting URL mapping...[/green]")

    results = map_urls(source_urls, dest_urls, use_web_content_check, rate_limit, output_file)
    
    output_df = pd.DataFrame(results, columns=['source', 'destination', 'confidence_score', 'remark'])
    output_df.to_csv(output_file, index=False, encoding='utf-8')
    
    console.log(f"[green][+] URL mapping completed. Output saved to {output_file}[/green]")
    console.print("[blue][+] Summary:[/blue]")
    console.print(f"[blue][+] Total Source URLs: {len(source_urls)}[/blue]")
    console.print(f"[blue][+] Total Destination URLs: {len(dest_urls)}[/blue]")
    console.print(f"[blue][+] Mapped URLs: {len(results)}[/blue]")

@click.command()
@click.option('--choice', type=click.Choice(['1', '0']), default=None, help='Menu choice: 1 to start URL redirection mapping, 0 to exit')
def redirection_genius(choice):
    """Powerful & intelligent redirect URL mapper."""
    while True:
        if not choice:
            console.print(Panel("Welcome to RedirectGenius\nPowerful and intelligent URL to URL redirection mapper", title="RedirectGenius", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))
            console.print("[yellow]1. Start URL redirection mapping[/yellow]")
            console.print("[red]0. Exit[/red]")
            
            choice = click.prompt(click.style("Please choose an option", fg="yellow", bold=True), type=int)

        if choice == 1:
            start_redirection()
        elif choice == 0:
            console.print("[bold red]Thank you for using RedirectGenius![/bold red]")
            break
        else:
            console.print("[bold red][-] Invalid choice! Please try again.[/bold red]")
            choice = None

if __name__ == "__main__":
    redirection_genius()

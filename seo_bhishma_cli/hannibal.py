import os
import sys
import click
import subprocess
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR
from rich.progress import Progress
from datetime import datetime
import pandas as pd
import numpy as np
from difflib import SequenceMatcher

console = Console()

# Function to check if a package is installed
def is_package_installed(package_name):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "show", package_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

# Function to install larger dependencies
def install_large_dependencies():
    console.print("[green][+] Installing large dependencies...[/green]")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "sentence-transformers", "scikit-learn"])
    console.print("[green][+] Large dependencies installed successfully.[/green]")

# Function to calculate package size
def calculate_package_size(package_name):
    result = subprocess.run([sys.executable, "-m", "pip", "show", package_name], capture_output=True, text=True)
    location_line = next((line for line in result.stdout.split('\n') if line.startswith("Location:")), None)
    if location_line:
        location = location_line.split(": ")[1]
        total_size = sum(os.path.getsize(os.path.join(dirpath, filename)) for dirpath, _, filenames in os.walk(location) for filename in filenames)
        return total_size / (1024 * 1024)  # Convert to MB
    return 0

# Function to check and install dependencies
def check_and_install_dependencies():
    required_large_packages = ["sentence-transformers", "scikit-learn"]
    large_dependencies_needed = any(not is_package_installed(pkg) for pkg in required_large_packages)

    if large_dependencies_needed:
        package_sizes = {pkg: calculate_package_size(pkg) for pkg in required_large_packages}
        total_size = sum(package_sizes.values())
        console.print(Panel(
            f"This tool requires additional large dependencies:\n"
            f"- sentence-transformers (~{package_sizes['sentence-transformers']:.2f} MB)\n"
            f"- scikit-learn (~{package_sizes['scikit-learn']:.2f} MB)\n\n"
            f"Estimated total download size: ~{total_size:.2f} MB\n"
            f"RAM required: ~2 GB\n",
            title="Dependency Required",
            border_style="green"
        ))
        confirm = Prompt.ask("Do you want to proceed with the installation? (yes/no)", default="yes")
        if confirm.lower() in ['yes', 'y']:
            install_large_dependencies()
        else:
            console.print("[bold red][-] Installation aborted by user.[/bold red]")
            return False
    return True

# Function to load GSC data from CSV file
def load_data(file_path):
    console.log("[+] Loading data from CSV file...")
    try:
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip().str.lower()
        return df
    except Exception as e:
        console.print(f"[bold red][-] Error loading CSV file: {e}[/bold red]")
        sys.exit(1)

# Function to aggregate data by page
def aggregate_data(df):
    console.log("[+] Aggregating data by page...")
    try:
        aggregated_df = df.groupby('page').agg({
            'query': lambda x: list(x),
            'clicks': 'sum',
            'impressions': 'sum',
            'ctr': 'mean',
            'position': 'mean'
        }).reset_index()
        return aggregated_df
    except Exception as e:
        console.print(f"[bold red][-] Error aggregating data: {e}[/bold red]")
        sys.exit(1)

# Function to compute URL slug similarity
def compute_slug_similarity(slug1, slug2):
    return SequenceMatcher(None, slug1, slug2).ratio()

# Function to compute embeddings for queries and URL slugs using an advanced multilingual transformer model
def get_embeddings(data, batch_size=64):
    from sentence_transformers import SentenceTransformer
    console.log("[+] Generating embeddings for queries and URL slugs...")
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    combined_text = (data['query'].apply(lambda x: ' '.join(x)).astype(str) + " " + data['page'].astype(str)).tolist()
    embeddings = []

    with Progress() as progress:
        task = progress.add_task("[green]Generating embeddings...", total=len(combined_text))
        for i in range(0, len(combined_text), batch_size):
            batch_embeddings = model.encode(combined_text[i:i+batch_size])
            embeddings.extend(batch_embeddings)
            progress.advance(task, batch_size)
    
    console.log("[+] Embeddings generation complete.")
    return np.array(embeddings)

# Function for dimensionality reduction using PCA
def reduce_dimensionality(embeddings, n_components=100):
    from sklearn.decomposition import PCA
    console.log("[+] Reducing dimensionality of embeddings...")
    pca = PCA(n_components=n_components)
    
    with Progress() as progress:
        task = progress.add_task("[green]Reducing dimensionality...", total=embeddings.shape[0])
        reduced_embeddings = pca.fit_transform(embeddings)
        progress.advance(task, embeddings.shape[0])
    
    console.log("[+] Dimensionality reduction complete.")
    return reduced_embeddings

# Function to compute semantic similarity using embeddings
def compute_similarity(embedding1, embedding2):
    return np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))

# Function to cluster URLs using exact match and optional slug similarity
def cluster_urls(df, embeddings, exact_match_threshold, semantic_match_threshold, use_semantic_check, slug_similarity_threshold, use_slug_similarity):
    console.log("[+] Clustering URLs...")
    clusters = []
    processed_urls = set()

    if use_semantic_check:
        from sklearn.cluster import AgglomerativeClustering
        clustering_model = AgglomerativeClustering(n_clusters=None, distance_threshold=semantic_match_threshold)
        labels = clustering_model.fit_predict(embeddings)
        unique_labels = np.unique(labels)

        for label in unique_labels:
            cluster = df['page'].iloc[np.where(labels == label)[0]].tolist()
            clusters.append(cluster)
    else:
        url_groups = df.groupby('page')
        with Progress() as progress:
            task = progress.add_task("[green]Clustering URLs...", total=len(url_groups))
            for primary_url, primary_data in url_groups:
                if primary_url in processed_urls:
                    progress.advance(task)
                    continue

                cluster = [primary_url]
                processed_urls.add(primary_url)

                for competing_url, competing_data in url_groups:
                    if competing_url in processed_urls or competing_url == primary_url:
                        continue

                    exact_match_queries = set(primary_data['query'].values[0]).intersection(set(competing_data['query'].values[0]))
                    exact_match_ratio = len(exact_match_queries) / len(primary_data['query'].values[0])
                    slug_similarity = compute_slug_similarity(primary_url, competing_url) if use_slug_similarity else 0

                    if exact_match_ratio >= exact_match_threshold or slug_similarity >= slug_similarity_threshold:
                        cluster.append(competing_url)
                        processed_urls.add(competing_url)

                clusters.append(cluster)
                progress.advance(task)

    return clusters

# Function to select primary URLs within clusters
def select_primary_urls(clusters, df, impression_share_threshold, click_share_threshold, query_share_threshold):
    primary_urls = []

    for cluster in clusters:
        if len(cluster) == 1:
            primary_urls.append({
                'Primary URL': cluster[0],
                'Competing URL': "NA",
                'Exact Match Queries': "NA",
                'Query Share %': "NA",
                'Click Share %': "NA",
                'Impression Share %': "NA",
                'Action': 'Keep as Primary URL',
                'Primary Clicks': df[df['page'] == cluster[0]]['clicks'].sum(),
                'Primary Impressions': df[df['page'] == cluster[0]]['impressions'].sum(),
                'Primary CTR': df[df['page'] == cluster[0]]['ctr'].mean(),
                'Primary Position': df[df['page'] == cluster[0]]['position'].mean(),
                'Competing Clicks': "NA",
                'Competing Impressions': "NA",
                'Competing CTR': "NA",
                'Competing Position': "NA"
            })
            continue

        # Select the URL with the highest total clicks as the primary URL initially
        best_url = max(cluster, key=lambda url: df[df['page'] == url]['clicks'].sum())

        for url in cluster:
            if url == best_url:
                continue

            primary_data = df[df['page'] == best_url]
            competing_data = df[df['page'] == url]
            exact_match_queries = set(primary_data['query'].values[0]).intersection(set(competing_data['query'].values[0]))

            matching_primary_clicks = primary_data[primary_data['query'].apply(lambda x: any(q in exact_match_queries for q in x))]['clicks'].sum()
            matching_primary_impressions = primary_data[primary_data['query'].apply(lambda x: any(q in exact_match_queries for q in x))]['impressions'].sum()
            
            matching_competing_clicks = competing_data[competing_data['query'].apply(lambda x: any(q in exact_match_queries for q in x))]['clicks'].sum()
            matching_competing_impressions = competing_data[competing_data['query'].apply(lambda x: any(q in exact_match_queries for q in x))]['impressions'].sum()

            # Calculate query share
            query_share = (len(exact_match_queries) / len(primary_data['query'].values[0])) * 100 if len(primary_data['query'].values[0]) > 0 else 0

            # Ensure the primary URL's matching queries have at least 80% of total clicks and impressions
            if matching_primary_clicks < 0.8 * primary_data['clicks'].sum() or matching_primary_impressions < 0.8 * primary_data['impressions'].sum():
                continue

            click_share = (matching_competing_clicks / matching_primary_clicks) * 100 if matching_primary_clicks > 0 else 0
            impression_share = (matching_competing_impressions / matching_primary_impressions) * 100 if matching_primary_impressions > 0 else 0

            # Check if competing URL should be the primary URL
            if matching_competing_clicks > matching_primary_clicks and matching_competing_impressions > matching_primary_impressions:
                best_url = url
                primary_data = df[df['page'] == best_url]
                matching_primary_clicks = matching_competing_clicks
                matching_primary_impressions = matching_competing_impressions

            # Check if the query share meets the threshold
            if query_share < query_share_threshold:
                continue

            if impression_share >= impression_share_threshold or click_share >= click_share_threshold:
                primary_urls.append({
                    'Primary URL': best_url,
                    'Competing URL': url,
                    'Exact Match Queries': ", ".join(exact_match_queries) if exact_match_queries else "NA",
                    'Query Share %': query_share,
                    'Click Share %': click_share,
                    'Impression Share %': impression_share,
                    'Action': 'Merge into Primary URL',
                    'Primary Clicks': primary_data['clicks'].sum(),
                    'Primary Impressions': primary_data['impressions'].sum(),
                    'Primary CTR': primary_data['ctr'].mean(),
                    'Primary Position': primary_data['position'].mean(),
                    'Competing Clicks': competing_data['clicks'].sum(),
                    'Competing Impressions': competing_data['impressions'].sum(),
                    'Competing CTR': competing_data['ctr'].mean(),
                    'Competing Position': competing_data['position'].mean(),
                    'Matching Primary Clicks': matching_primary_clicks,
                    'Matching Primary Impressions': matching_primary_impressions,
                    'Matching Competing Clicks': matching_competing_clicks,
                    'Matching Competing Impressions': matching_competing_impressions
                })

        # Add the final primary URL if no competing URL has been added
        if not any(item['Primary URL'] == best_url for item in primary_urls):
            primary_urls.append({
                'Primary URL': best_url,
                'Competing URL': "NA",
                'Exact Match Queries': "NA",
                'Query Share %': "NA",
                'Click Share %': "NA",
                'Impression Share %': "NA",
                'Action': 'Keep as Primary URL',
                'Primary Clicks': df[df['page'] == best_url]['clicks'].sum(),
                'Primary Impressions': df[df['page'] == best_url]['impressions'].sum(),
                'Primary CTR': df[df['page'] == best_url]['ctr'].mean(),
                'Primary Position': df[df['page'] == best_url]['position'].mean(),
                'Competing Clicks': "NA",
                'Competing Impressions': "NA",
                'Competing CTR': "NA",
                'Competing Position': "NA",
                'Matching Primary Clicks': "NA",
                'Matching Primary Impressions': "NA",
                'Matching Competing Clicks': "NA",
                'Matching Competing Impressions': "NA"
            })

    return primary_urls

# Function to save cannibalization report to CSV
def save_cannibalization_report(report, output_file):
    console.log(f"[+] Saving cannibalization report to {output_file}...")
    report_df = pd.DataFrame(report, columns=[
        'Primary URL', 'Competing URL', 'Exact Match Queries', 'Query Share %', 'Click Share %', 'Impression Share %', 'Action',
        'Primary Clicks', 'Primary Impressions', 'Primary CTR', 'Primary Position',
        'Competing Clicks', 'Competing Impressions', 'Competing CTR', 'Competing Position',
        'Matching Primary Clicks', 'Matching Primary Impressions', 'Matching Competing Clicks', 'Matching Competing Impressions'
    ])
    report_df.to_csv(output_file, index=False)

@click.command()
@click.option('--input-csv', default=None, help='Path to the input CSV file containing URLs')
@click.option('--output-csv', default=f'cannibalization_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv', show_default=True, help='Path to save the output cannibalization report CSV file.')
@click.option('--exact-match-threshold', default=0.2, help='Threshold for exact match query ratio.')
@click.option('--impression-share-threshold', default=0.7, help='Threshold for impression share of exact match queries.')
@click.option('--click-share-threshold', default=0.2, help='Threshold for click share of exact match queries.')
@click.option('--query-share-threshold', default=25, help='Threshold for query share.')
@click.option('--use-slug-similarity', is_flag=True, default=False, help='Enable URL slug similarity check')
@click.option('--slug-similarity-threshold', default=0.5, help='Threshold for URL slug similarity.')
@click.option('--use-semantic-check', is_flag=True, default=False, help='Enable semantic check.')
def hannibal(input_csv, output_csv, exact_match_threshold, impression_share_threshold, click_share_threshold, query_share_threshold, use_slug_similarity, slug_similarity_threshold, use_semantic_check):
    """Identifies URL cannibalization issues using GSC data"""
    console.print(Panel("Welcome to Hannibal\nIdentifies URL cannibalization issues using GSC data.", title="Hannibal", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))

    if not input_csv:
        input_csv = click.prompt(click.style("Enter the path to the input CSV file", fg="cyan"), default="input.csv", show_default=True)
    
    if exact_match_threshold == 0.2:
        exact_match_threshold = float(click.prompt(click.style("Enter the threshold for exact match query ratio", fg="cyan"), default=0.2, show_default=True))
        
    if impression_share_threshold == 0.7:
        impression_share_threshold = float(click.prompt(click.style("Enter the threshold for impression share of exact match queries", fg="cyan"), default=0.7, show_default=True))
    
    if click_share_threshold == 0.2:
        click_share_threshold = float(click.prompt(click.style("Enter the threshold for click share of exact match queries", fg="cyan"), default=0.2, show_default=True))
        
    if query_share_threshold == 25:
        query_share_threshold = int(click.prompt(click.style("Enter the threshold for query share", fg="cyan"), default=25, show_default=True))
    
    if not use_slug_similarity:
        use_slug_similarity = click.prompt(click.style("Enable URL slug similarity check (yes/no)", fg="cyan"), default="no", show_default=True) == "yes"
        if use_slug_similarity:
            slug_similarity_threshold = float(click.prompt(click.style("Enter the threshold for URL slug similarity", fg="cyan"), default=0.5, show_default=True))
    
    if not use_semantic_check:
        use_semantic_check = click.prompt(click.style("Enable semantic check (yes/no)", fg="cyan"), default="no", show_default=True) == "yes"
        
    # Check and install dependencies if required
    if use_semantic_check or use_slug_similarity:
        if not check_and_install_dependencies():
            return

    console.print(f"\n[green][+] Starting cannibalization detection process...[/green]")

    # Load data
    df = load_data(input_csv)

    # Convert columns to numeric
    console.print("[green][+] Converting columns to numeric...[/green]")
    df['clicks'] = df['clicks'].astype(str).str.replace(',', '').astype(float)
    df['impressions'] = df['impressions'].astype(str).str.replace(',', '').astype(float)
    df['ctr'] = df['ctr'].astype(str).str.replace('%', '').astype(float) / 100
    df['position'] = df['position'].astype(float)

    # Aggregate data by page
    aggregated_df = aggregate_data(df)

    # Get embeddings if semantic check is enabled
    embeddings = None
    if use_semantic_check:
        embeddings = get_embeddings(aggregated_df)
        embeddings = reduce_dimensionality(embeddings)

    # Clustering URLs
    clusters = cluster_urls(aggregated_df, embeddings, exact_match_threshold, slug_similarity_threshold, use_semantic_check, slug_similarity_threshold, use_slug_similarity)

    # Selecting Primary URLs
    cannibalization_report = select_primary_urls(clusters, aggregated_df, impression_share_threshold, click_share_threshold, query_share_threshold)

    # Save cannibalization report
    save_cannibalization_report(cannibalization_report, output_csv)

    console.print(f"[bold green][+] Cannibalization report saved to '{output_csv}'[/bold green] \n")

if __name__ == "__main__":
    hannibal()

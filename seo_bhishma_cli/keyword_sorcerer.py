from openai import OpenAI
import click
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN, SpectralClustering
from sklearn.metrics import silhouette_score
from datetime import datetime
from rich.panel import Panel
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR
import os
import numpy as np
import time
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Prompt
import logging

# Suppress detailed httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)

CONFIG_FILE = 'config.yaml'
PROGRESS_FILE = 'progress.yaml'

console = Console()

# Function to load configuration
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as file:
            config = yaml.safe_load(file)
    else:
        config = {}
    return config

# Function to save configuration
def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as file:
        yaml.safe_dump(config, file)

# Function to save progress
def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as file:
        yaml.safe_dump(progress, file)

# Function to load progress
def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as file:
            progress = yaml.safe_load(file)
    else:
        progress = {}
    return progress

# Function to load keywords from CSV file
def load_keywords(file_path):
    df = pd.read_csv(file_path)
    if 'keywords' not in df.columns or 'search_volume' not in df.columns:
        raise ValueError("[-] Input CSV must contain 'keywords' and 'search_volume' columns")
    return df

# Function to estimate token usage
def estimate_token_usage(keywords):
    fixed_prompt_tokens = 11  # "Generate an embedding for the keyword: " (~11 tokens)
    avg_keyword_tokens = 5  # Average length of keyword (~5 tokens)
    response_tokens = 50  # Estimated response length
    tokens_per_keyword = fixed_prompt_tokens + avg_keyword_tokens + response_tokens
    total_tokens = len(keywords) * tokens_per_keyword
    return total_tokens

# Function to determine cluster names based on keywords
def determine_cluster_names(keywords, labels):
    clusters = {}
    for label in set(labels):
        cluster_keywords = [keywords[i] for i in range(len(keywords)) if labels[i] == label]
        cluster_name = max(set(cluster_keywords), key=cluster_keywords.count)
        clusters[label] = cluster_name
    return clusters

# Function to generate embeddings for keywords using OpenAI GPT-4
def generate_embeddings(keywords, api_key):
    client = OpenAI(api_key=api_key)
    embeddings = []
    progress = load_progress()
    start_index = progress.get('start_index', 0)
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TimeRemainingColumn()) as progress_bar:
        task = progress_bar.add_task("[green][+] Generating embeddings", total=len(keywords) - start_index)
        for i, keyword in enumerate(keywords[start_index:], start=start_index):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": f"Generate a descriptive sentence that captures the intent for the keyword: {keyword}"}
                    ],
                    max_tokens=50
                )
                embedding = response.choices[0].message.content.strip()
                embeddings.append(embedding)
                progress_bar.update(task, advance=1)
                progress['start_index'] = i + 1
                save_progress(progress)
                time.sleep(0.5)  # Rate limiting
            except Exception as e:
                console.print(f"[red][-] Error generating embedding for '{keyword}': {e}")
                embeddings.append('')
    return embeddings

# Function to calculate the optimal number of clusters
def calculate_optimal_clusters(n_keywords, min_keywords_per_cluster=4, max_keywords_per_cluster=8):
    min_clusters = max(1, n_keywords // max_keywords_per_cluster)
    max_clusters = max(1, n_keywords // min_keywords_per_cluster)
    return min_clusters, max_clusters

# Function to cluster keywords using KMeans
def cluster_keywords_kmeans(embeddings, min_clusters, max_clusters):
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    best_score = -1
    best_labels = None
    for n_clusters in range(min_clusters, max_clusters + 1):
        model = KMeans(n_clusters=n_clusters, random_state=42)
        labels = model.fit_predict(X)
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score = score
            best_labels = labels
    return best_labels, best_score

# Function to cluster keywords using Agglomerative Clustering
def cluster_keywords_agglomerative(embeddings, min_clusters, max_clusters):
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    best_score = -1
    best_labels = None
    for n_clusters in range(min_clusters, max_clusters + 1):
        model = AgglomerativeClustering(n_clusters=n_clusters)
        labels = model.fit_predict(X.toarray())
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score = score
            best_labels = labels
    return best_labels, best_score

# Function to cluster keywords using DBSCAN
def cluster_keywords_dbscan(embeddings):
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    model = DBSCAN(eps=0.5, min_samples=5)
    labels = model.fit_predict(X)
    try:
        score = silhouette_score(X, labels)
    except ValueError as e:
        console.print(f"[yellow][/] Warning: {e}")
        score = None
    return labels, score

# Function to cluster keywords using Spectral Clustering
def cluster_keywords_spectral(embeddings, min_clusters, max_clusters):
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    best_score = -1
    best_labels = None
    for n_clusters in range(min_clusters, max_clusters + 1):
        model = SpectralClustering(n_clusters=n_clusters, affinity='nearest_neighbors', random_state=42)
        labels = model.fit_predict(X)
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score = score
            best_labels = labels
    return best_labels, best_score

# Function to save clustered keywords to CSV
def save_clusters_to_csv(df, labels, clusters, scores, output_file):
    df['keyword_theme'] = [clusters[label] for label in labels]
    df['confidence_score'] = scores
    df.to_csv(output_file, index=False, encoding='utf-8')

@click.command()
@click.pass_context
def keyword_sorcerer(ctx):
    """Cluster keywords based on semantic relevance."""
    config = load_config()
    
    while True:
        console.print(Panel("Keyword Sorcerer\nKeyword clusterizer powered by GPT-4o", title="Keyword Sorcerer", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))
        console.print("[cyan]1. Cluster keywords with KMeans")
        console.print("[cyan]2. Cluster keywords with Agglomerative Clustering")
        console.print("[cyan]3. Cluster keywords with DBSCAN")
        console.print("[cyan]4. Cluster keywords with Spectral Clustering")
        console.print("[red bold]0. Exit")
        choice = Prompt.ask("[cyan bold]Enter your choice", default="0")

        if choice == "0":
            console.print("[red bold]Exiting Keyword Sorcerer. Goodbye!")
            break
        elif choice in ["1", "2", "3", "4"]:
            input_file = Prompt.ask("[cyan]Enter the path to the input CSV file", default="keywords.csv")
            output_file = Prompt.ask("[cyan]Enter the path to the output CSV file", default=f"clusters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            
            if 'api_key' not in config:
                api_key = Prompt.ask("[cyan]Enter your OpenAI API key", password=True)
                config['api_key'] = api_key
                save_config(config)
            else:
                api_key = config['api_key']

            console.print("[green bold][+] Loading keywords...")
            try:
                df = load_keywords(input_file)
            except Exception as e:
                console.print(f"[red][-] Error loading keywords: {e}")
                continue

            total_tokens = estimate_token_usage(df['keywords'].tolist())
            estimated_cost = (total_tokens / 1000) * 0.02  # Assuming $0.02 per 1000 tokens
            console.print(f"[green]Estimated token usage: {total_tokens}")
            console.print(f"[green]Estimated cost: ${estimated_cost:.4f}")

            proceed = Prompt.ask("[cyan]Do you want to proceed?", default="no")
            if proceed.lower() != "yes":
                console.print("[red][-] Operation cancelled by user.")
                continue

            console.print("[green bold][+] Generating embeddings...")
            try:
                embeddings = generate_embeddings(df['keywords'].tolist(), api_key)
                if not any(embeddings):
                    raise ValueError("[-] All embeddings are empty. Check the input data or OpenAI responses.")
            except Exception as e:
                console.print(f"[red][-] Error generating embeddings: {e}")
                continue

            min_clusters, max_clusters = calculate_optimal_clusters(len(df), min_keywords_per_cluster=4, max_keywords_per_cluster=8)

            console.print("[green bold][+] Clustering keywords...")
            try:
                if choice == "1":
                    labels, score = cluster_keywords_kmeans(embeddings, min_clusters, max_clusters)
                elif choice == "2":
                    labels, score = cluster_keywords_agglomerative(embeddings, min_clusters, max_clusters)
                elif choice == "3":
                    labels, score = cluster_keywords_dbscan(embeddings)
                elif choice == "4":
                    labels, score = cluster_keywords_spectral(embeddings, min_clusters, max_clusters)
                else:
                    console.print("[red][-] Invalid choice. Please select a valid option.")
                    continue
                clusters = determine_cluster_names(df['keywords'], labels)
            except Exception as e:
                console.print(f"[red][-] Error clustering keywords: {e}")
                continue

            console.print("[green bold][+] Saving clustered keywords...")
            try:
                save_clusters_to_csv(df, labels, clusters, [score] * len(labels), output_file)
            except Exception as e:
                console.print(f"[red][-] Error saving clustered keywords: {e}")
                continue

            console.print(f"[green bold][+] Keyword clustering complete. {len(clusters)} clusters created for {len(df)} keywords.")
        else:
            console.print("[red][-] Invalid choice. Please select a valid option.")

        console.print("\n" + "="*50 + "\n")

if __name__ == '__main__':
    keyword_sorcerer()

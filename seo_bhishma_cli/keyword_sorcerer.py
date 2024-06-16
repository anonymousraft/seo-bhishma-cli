from openai import OpenAI
import click
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN, SpectralClustering
from sklearn.metrics import silhouette_score
from tqdm import tqdm
from datetime import datetime
import os
import numpy as np
import time
import yaml

CONFIG_FILE = 'config.yaml'

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
    with open(CONFIG_FILE, 'w') as file:
        yaml.safe_dump(config, file)

# Function to load keywords from CSV file
def load_keywords(file_path):
    df = pd.read_csv(file_path)
    if 'keywords' not in df.columns or 'search_volume' not in df.columns:
        raise ValueError("Input CSV must contain 'keywords' and 'search_volume' columns")
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
    for keyword in tqdm(keywords, desc="Generating embeddings"):
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
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"Error generating embedding for '{keyword}': {e}")
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
        print(f"Warning: {e}")
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
    df.to_csv(output_file, index=False)

@click.command()
@click.pass_context
def keyword_sorcerer(ctx):
    """Cluster keywords based on semantic relevance."""
    config = load_config()
    
    while True:
        click.echo("\n" + "="*50)
        click.echo(click.style("Keyword Sorcerer", fg="yellow", bold=True))
        click.echo(click.style("1. Cluster keywords with KMeans", fg="cyan"))
        click.echo(click.style("2. Cluster keywords with Agglomerative Clustering", fg="cyan"))
        click.echo(click.style("3. Cluster keywords with DBSCAN", fg="cyan"))
        click.echo(click.style("4. Cluster keywords with Spectral Clustering", fg="cyan"))
        click.echo(click.style("0. Exit", fg="red", bold=True))
        choice = click.prompt(click.style("Enter your choice", fg="cyan", bold=True), type=int)

        if choice == 0:
            click.echo(click.style("Exiting Keyword Sorcerer. Goodbye!", fg="red", bold=True))
            break
        elif choice in [1, 2, 3, 4]:
            input_file = click.prompt(click.style("Enter the path to the input CSV file", fg="cyan"), type=click.Path(exists=True))
            output_file = click.prompt(click.style("Enter the path to the output CSV file", fg="cyan"), default=f"clusters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", type=click.Path())
            
            if 'api_key' not in config:
                api_key = click.prompt(click.style("Enter your OpenAI API key", fg="cyan"), hide_input=True)
                config['api_key'] = api_key
                save_config(config)
            else:
                api_key = config['api_key']

            click.echo(click.style("Loading keywords...", fg="green", bold=True))
            try:
                df = load_keywords(input_file)
            except Exception as e:
                click.echo(click.style(f"Error loading keywords: {e}", fg="red"))
                continue

            total_tokens = estimate_token_usage(df['keywords'].tolist())
            estimated_cost = (total_tokens / 1000) * 0.02  # Assuming $0.02 per 1000 tokens
            click.echo(click.style(f"Estimated token usage: {total_tokens}", fg="green"))
            click.echo(click.style(f"Estimated cost: ${estimated_cost:.4f}", fg="green"))

            proceed = click.confirm(click.style("Do you want to proceed?", fg="cyan"))
            if not proceed:
                click.echo(click.style("Operation cancelled by user.", fg="red"))
                continue

            click.echo(click.style("Generating embeddings...", fg="green", bold=True))
            try:
                embeddings = generate_embeddings(df['keywords'].tolist(), api_key)
                if not any(embeddings):
                    raise ValueError("All embeddings are empty. Check the input data or OpenAI responses.")
            except Exception as e:
                click.echo(click.style(f"Error generating embeddings: {e}", fg="red"))
                continue

            min_clusters, max_clusters = calculate_optimal_clusters(len(df), min_keywords_per_cluster=4, max_keywords_per_cluster=8)

            click.echo(click.style("Clustering keywords...", fg="green", bold=True))
            try:
                if choice == 1:
                    labels, score = cluster_keywords_kmeans(embeddings, min_clusters, max_clusters)
                elif choice == 2:
                    labels, score = cluster_keywords_agglomerative(embeddings, min_clusters, max_clusters)
                elif choice == 3:
                    labels, score = cluster_keywords_dbscan(embeddings)
                elif choice == 4:
                    labels, score = cluster_keywords_spectral(embeddings, min_clusters, max_clusters)
                else:
                    click.echo(click.style("Invalid choice. Please select a valid option.", fg="red"))
                    continue
                clusters = determine_cluster_names(df['keywords'], labels)
            except Exception as e:
                click.echo(click.style(f"Error clustering keywords: {e}", fg="red"))
                continue

            click.echo(click.style("Saving clustered keywords...", fg="green", bold=True))
            try:
                save_clusters_to_csv(df, labels, clusters, [score] * len(labels), output_file)
            except Exception as e:
                click.echo(click.style(f"Error saving clustered keywords: {e}", fg="red"))
                continue

            click.echo(click.style(f"Keyword clustering complete. {len(clusters)} clusters created for {len(df)} keywords.", fg="green", bold=True))
        else:
            click.echo(click.style("Invalid choice. Please select a valid option.", fg="red"))

        click.echo("\n" + "="*50 + "\n")

if __name__ == '__main__':
    keyword_sorcerer()

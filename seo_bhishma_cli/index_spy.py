import requests
import pandas as pd
import click

def read_input_file(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    elif file_path.endswith('.json'):
        return pd.read_json(file_path)
    else:
        raise ValueError("Unsupported file format. Use CSV or JSON.")

def check_indexing_status(url):
    query = f"site:{url}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
    response = requests.get(f"https://www.google.com/search?q={query}", headers=headers)
    return "Indexed" if "did not match any documents" not in response.text else "Not Indexed"

@click.command()
def index_spy():
    """Check the indexing status of a list of URLs."""
    input_file = click.prompt(click.style("Enter the path to the input file (CSV/JSON)", fg="cyan", bold=True), type=click.Path(exists=True))
    output_file = click.prompt(click.style("Enter the path to the output CSV file", fg="cyan", bold=True), type=click.Path())
    
    data = read_input_file(input_file)
    results = []
    
    for url in data['url']:
        status = check_indexing_status(url)
        results.append({
            'url': url,
            'status': status
        })
    
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    print(click.style(f"Indexing status report saved to {output_file}", fg="green", bold=True))

import requests
import pandas as pd
import click
import random
import time
from tqdm import tqdm
from itertools import cycle
from bs4 import BeautifulSoup
from datetime import datetime

# Load user agents from a file
def load_user_agents(user_agent_file):
    with open(user_agent_file, 'r') as f:
        user_agents = f.read().splitlines()
    return user_agents

# Load proxies from a file
def load_proxies(proxy_file):
    with open(proxy_file, 'r') as f:
        proxies = f.read().splitlines()
    return proxies

# Validate proxy by making a simple request
def validate_proxy(proxy, user_agent):
    proxies = {
        'http': f"http://{proxy}",
        'https': f"https://{proxy}"
    }
    headers = {'User-Agent': user_agent}
    test_url = "https://www.google.com"
    try:
        response = requests.get(test_url, headers=headers, proxies=proxies, timeout=10)
        if response.status_code == 200 and "captcha" not in response.text.lower():
            return proxies
    except Exception:
        pass
    
    # Try only HTTP
    proxies = {
        'http': f"http://{proxy}"
    }
    try:
        response = requests.get(test_url, headers=headers, proxies=proxies, timeout=10)
        if response.status_code == 200 and "captcha" not in response.text.lower():
            return proxies
    except Exception:
        pass
    
    # Try only HTTPS
    proxies = {
        'https': f"https://{proxy}"
    }
    try:
        response = requests.get(test_url, headers=headers, proxies=proxies, timeout=10)
        if response.status_code == 200 and "captcha" not in response.text.lower():
            return proxies
    except Exception:
        return None

# Check indexing status using a proxy and user-agent
def check_indexing_status(url, proxies=None, user_agent=None):
    query = f"site:{url}"
    headers = {'User-Agent': user_agent} if user_agent else {}
    search_url = f"https://www.google.com/search?q={query}"

    try:
        response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
        if "captcha" in response.text.lower():
            return "Captcha Encountered"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('div', class_='g')
        
        if results:
            return "Indexed"
        else:
            return "Not Indexed"
    except Exception as e:
        return f"Error: {e}"

# Read input file (CSV or JSON)
def read_input_file(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    elif file_path.endswith('.json'):
        return pd.read_json(file_path)
    else:
        raise ValueError("Unsupported file format. Use CSV or JSON.")

# Index Spy CLI command
@click.command()
@click.pass_context
def index_spy(ctx):
    """Check if URLs are indexed by Google."""
    use_proxy = click.confirm("Do you want to use proxies?", default=False)
    proxy_file = None
    proxies = None
    valid_proxies = None
    current_proxy = None
    if use_proxy:
        proxy_file = click.prompt("Enter the path to the proxy file", type=click.Path(exists=True))
        proxies = cycle(load_proxies(proxy_file))
        
    use_user_agent = click.confirm("Do you want to randomize user agents?", default=False)
    user_agents = None
    current_user_agent = None
    if use_user_agent:
        user_agent_file = click.prompt("Enter the path to the user agent file", type=click.Path(exists=True))
        user_agents = load_user_agents(user_agent_file)
    
    while True:
        click.echo("\n" + "="*50)
        click.echo(click.style("IndexSpy - Bulk Indexing Checker", fg="yellow", bold=True))
        click.echo(click.style("1. Check a single URL", fg="cyan"))
        click.echo(click.style("2. Check URLs from a file", fg="cyan"))
        click.echo(click.style("3. Exit", fg="red", bold=True))
        choice = click.prompt(click.style("Enter your choice", fg="cyan", bold=True), type=int)

        if choice == 1:
            url = click.prompt(click.style("Enter the URL to check indexing status", fg="cyan"))
            if use_proxy:
                while True:
                    proxy = next(proxies)
                    valid_proxies = validate_proxy(proxy, random.choice(user_agents) if user_agents else None)
                    if valid_proxies:
                        current_proxy = proxy
                        click.echo(click.style(f"Using Proxy: {current_proxy}", fg="blue"))
                        break
                    else:
                        click.echo(click.style(f"Proxy {proxy} is not valid. Skipping.", fg="red"))
            
            user_agent = random.choice(user_agents) if use_user_agent else None
            if user_agent != current_user_agent:
                current_user_agent = user_agent
                click.echo(click.style(f"Using User-Agent: {current_user_agent}", fg="blue"))

            status = check_indexing_status(url, valid_proxies, current_user_agent)
            click.echo(click.style(f"URL: {url}", fg="cyan"))
            click.echo(click.style(f"Indexing Status: {status}", fg="green" if status == "Indexed" else "red"))
        
        elif choice == 2:
            input_file = click.prompt(click.style("Enter the path to the input file (CSV/JSON)", fg="cyan"), type=click.Path(exists=True))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_output_file = f"index_spy_output_{timestamp}.csv"
            output_file = click.prompt(click.style("Enter the path to the output CSV file", fg="cyan"), type=click.Path(), default=default_output_file)
            data = read_input_file(input_file)
            results = []
            
            if use_proxy:
                while True:
                    proxy = next(proxies)
                    valid_proxies = validate_proxy(proxy, random.choice(user_agents) if user_agents else None)
                    if valid_proxies:
                        current_proxy = proxy
                        click.echo(click.style(f"Using Proxy: {current_proxy}", fg="blue"))
                        break
                    else:
                        click.echo(click.style(f"Proxy {proxy} is not valid. Skipping.", fg="red"))

            click.echo(click.style("Checking indexing status for URLs...", fg="green", bold=True))
            
            index = 0
            while index < len(data):
                url = data.loc[index, 'url']
                user_agent = random.choice(user_agents) if use_user_agent and user_agents else None
                if user_agent != current_user_agent:
                    current_user_agent = user_agent
                    click.echo(click.style(f"Using User-Agent: {current_user_agent}", fg="blue"))
                
                status = check_indexing_status(url, valid_proxies, current_user_agent)
                if "Captcha Encountered" in status:
                    click.echo(click.style("Captcha encountered! Rotating proxy and user agent.", fg="red"))
                    time.sleep(2)  # Wait a bit before retrying to avoid continuous captchas

                    # Rotate proxy and user agent until a valid one is found
                    while True:
                        if use_proxy:
                            proxy = next(proxies)
                            valid_proxies = validate_proxy(proxy, random.choice(user_agents) if user_agents else None)
                            if valid_proxies:
                                current_proxy = proxy
                                click.echo(click.style(f"Using Proxy: {current_proxy}", fg="blue"))
                                break
                            else:
                                click.echo(click.style(f"Proxy {proxy} is not valid. Skipping.", fg="red"))

                        user_agent = random.choice(user_agents) if use_user_agent and user_agents else None
                        if user_agent != current_user_agent:
                            current_user_agent = user_agent
                            click.echo(click.style(f"Using User-Agent: {current_user_agent}", fg="blue"))

                    # Re-check the current URL with new proxy and user agent
                    continue  # Continue with the same index after rotating proxy and user agent

                results.append({
                    'url': url,
                    'indexing_status': status,
                    'proxy': current_proxy,
                    'user_agent': current_user_agent
                })
                index += 1  # Move to the next URL only if no captcha was encountered

            df = pd.DataFrame(results)
            df.to_csv(output_file, index=False)
            click.echo(click.style(f"Indexing status saved to {output_file}", fg="green", bold=True))
        
        elif choice == 3:
            click.echo(click.style("Exiting IndexSpy. Goodbye!", fg="red", bold=True))
            break
        
        else:
            click.echo(click.style("Invalid choice. Please select a valid option.", fg="red"))

        click.echo("\n" + "="*50 + "\n")

if __name__ == "__main__":
    index_spy()

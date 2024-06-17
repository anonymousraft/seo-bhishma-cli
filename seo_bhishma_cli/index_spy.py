import requests
import pandas as pd
import click
import random
import time
from tqdm import tqdm
from itertools import cycle
from bs4 import BeautifulSoup
from datetime import datetime
import signal
import sys

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

# Validate proxy and user agent by making a search request
def validate_proxy_and_user_agent(proxy, user_agent, url, proxy_mode):
    headers = {'User-Agent': user_agent} if user_agent else {}
    for protocol in proxy_mode:
        proxies = {protocol: f"{protocol}://{proxy}"}
        try:
            response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
            if response.status_code == 200 and "captcha" not in response.text.lower():
                return proxies
            elif response.status_code == 429:
                click.echo(click.style(f"Proxy {proxy} returned 429 Too Many Requests. Applying delay...", fg="red"))
                time.sleep(60)  # Apply a delay if 429 is encountered
            else:
                click.echo(click.style(f"Proxy {proxy} returned status code {response.status_code}", fg="red"))
        except requests.RequestException as e:
            click.echo(click.style(f"Proxy {proxy} failed with error: {e}", fg="red"))
    return None

# Check indexing status using a proxy and user-agent
def check_indexing_status(url, proxies=None, user_agent=None, captcha_service=None, captcha_key=None, rate_limit=0):
    query = f"site:{url}"
    headers = {'User-Agent': user_agent} if user_agent else {}
    search_url = f"https://www.google.com/search?q={query}"

    try:
        response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
        if "captcha" in response.text.lower():
            if captcha_service and captcha_key:
                site_key = get_site_key(search_url)
                if site_key:
                    captcha_solution = solve_captcha(captcha_service, captcha_key, search_url, site_key)
                    if captcha_solution:
                        headers['g-recaptcha-response'] = captcha_solution
                        response = requests.get(search_url, headers=headers, proxies=proxies, timeout=10)
                        if "captcha" not in response.text.lower():
                            return parse_indexing_status(response)
            return "Captcha Encountered"
        
        return parse_indexing_status(response)
    except Exception as e:
        return f"Error: {e}"
    finally:
        if rate_limit > 0:
            click.echo(click.style(f"Applying rate limit: Waiting for {rate_limit} seconds...", fg="yellow"))
            time.sleep(rate_limit)

def parse_indexing_status(response):
    soup = BeautifulSoup(response.text, 'html.parser')
    results = soup.find_all('div', class_='g')
    
    if results:
        return "Indexed"
    else:
        return "Not Indexed"

def get_site_key(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    recaptcha_tag = soup.find('div', {'class': 'g-recaptcha'})
    if recaptcha_tag and 'data-sitekey' in recaptcha_tag.attrs:
        return recaptcha_tag['data-sitekey']
    return None

def solve_captcha_2captcha(api_key, google_search_url, site_key):
    captcha_request_url = "http://2captcha.com/in.php"
    captcha_response_url = "http://2captcha.com/res.php"
    payload = {
        'key': api_key,
        'method': 'userrecaptcha',
        'googlekey': site_key,
        'pageurl': google_search_url
    }
    response = requests.post(captcha_request_url, data=payload)
    
    if response.status_code != 200:
        raise Exception("Failed to send captcha solving request")

    response_text = response.text.split('|')
    if response_text[0] != 'OK':
        raise Exception(f"Error from 2Captcha: {response.text}")
    
    request_id = response_text[1]
    
    solution_payload = {
        'key': api_key,
        'action': 'get',
        'id': request_id
    }
    while True:
        solution_response = requests.get(captcha_response_url, params=solution_payload)
        solution_response_text = solution_response.text.split('|')
        if solution_response_text[0] == 'CAPCHA_NOT_READY':
            time.sleep(5)
            continue
        elif solution_response_text[0] == 'OK':
            return solution_response_text[1]
        else:
            raise Exception(f"Error solving captcha: {solution_response.text}")

def solve_captcha_anticaptcha(api_key, google_search_url, site_key):
    create_task_url = "https://api.anti-captcha.com/createTask"
    get_task_result_url = "https://api.anti-captcha.com/getTaskResult"
    
    task_payload = {
        "clientKey": api_key,
        "task": {
            "type": "NoCaptchaTaskProxyless",
            "websiteURL": google_search_url,
            "websiteKey": site_key
        }
    }
    response = requests.post(create_task_url, json=task_payload)
    
    if response.status_code != 200:
        raise Exception("Failed to send captcha solving request")

    response_json = response.json()
    if response_json.get('errorId') != 0:
        raise Exception(f"Error from Anti-Captcha: {response_json.get('errorDescription')}")

    task_id = response_json.get('taskId')
    
    solution_payload = {
        "clientKey": api_key,
        "taskId": task_id
    }
    while True:
        solution_response = requests.post(get_task_result_url, json=solution_payload)
        result = solution_response.json()
        if result['status'] == 'processing':
            time.sleep(5)
            continue
        elif result['status'] == 'ready':
            return result['solution']['gRecaptchaResponse']
        else:
            raise Exception(f"Error solving captcha: {result.get('errorDescription')}")

def solve_captcha(captcha_service, captcha_key, url, site_key):
    if captcha_service.lower() == '2captcha':
        return solve_captcha_2captcha(captcha_key, url, site_key)
    elif captcha_service.lower() == 'anti-captcha':
        return solve_captcha_anticaptcha(captcha_key, url, site_key)
    return None

def read_input_file(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    elif file_path.endswith('.json'):
        return pd.read_json(file_path)
    else:
        raise ValueError("Unsupported file format. Use CSV or JSON.")

def save_progress(results, output_file):
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    click.echo(click.style(f"Progress saved to {output_file}", fg="green", bold=True))

def signal_handler(sig, frame):
    click.echo(click.style("\nProcess interrupted! Saving progress...", fg="red", bold=True))
    save_progress(results, output_file)
    sys.exit(0)

@click.command()
@click.pass_context
def index_spy(ctx):
    """Check if URLs are indexed by Google."""
    global results, output_file

    use_proxy = click.confirm("Do you want to use proxies?", default=False)
    proxy_file = None
    proxies = None
    valid_proxies = None
    current_proxy = None
    proxy_mode = ['http', 'https']
    if use_proxy:
        proxy_file = click.prompt("Enter the path to the proxy file", type=click.Path(exists=True))
        proxies = cycle(load_proxies(proxy_file))
        proxy_mode_choice = click.prompt(
            "Select proxy mode",
            type=click.Choice(['HTTP', 'HTTPS', 'Both', 'SOCKS4', 'SOCKS5'], case_sensitive=False),
            default='Both'
        )
        if proxy_mode_choice.lower() == 'http':
            proxy_mode = ['http']
        elif proxy_mode_choice.lower() == 'https':
            proxy_mode = ['https']
        elif proxy_mode_choice.lower() == 'both':
            proxy_mode = ['http', 'https']
        elif proxy_mode_choice.lower() == 'socks4':
            proxy_mode = ['socks4']
        elif proxy_mode_choice.lower() == 'socks5':
            proxy_mode = ['socks5']
        
    use_user_agent = click.confirm("Do you want to randomize user agents?", default=False)
    user_agents = None
    current_user_agent = None
    if use_user_agent:
        user_agent_file = click.prompt("Enter the path to the user agent file", type=click.Path(exists=True))
        user_agents = load_user_agents(user_agent_file)
    
    use_captcha_service = click.confirm("Do you want to use a paid captcha solving service?", default=False)
    captcha_service = None
    captcha_key = None
    if use_captcha_service:
        captcha_service = click.prompt("Enter the captcha service (2Captcha or Anti-Captcha)", type=str, default='2Captcha')
        captcha_key = click.prompt("Enter your captcha service API key", type=str)

    rate_limit = click.prompt("Enter the delay between requests in seconds (0 for no delay)", type=int, default=0)

    validated = False
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        click.echo("\n" + "="*50)
        click.echo(click.style("IndexSpy - Bulk Indexing Checker", fg="yellow", bold=True))
        click.echo(click.style("1. Check a single URL", fg="cyan"))
        click.echo(click.style("2. Check URLs from a file", fg="cyan"))
        click.echo(click.style("3. Exit", fg="red", bold=True))
        choice = click.prompt(click.style("Enter your choice", fg="cyan", bold=True), type=int)

        if choice == 1:
            url = click.prompt(click.style("Enter the URL to check indexing status", fg="cyan"))
            if use_proxy or use_user_agent:
                while not validated:
                    proxy = next(proxies) if use_proxy else None
                    user_agent = random.choice(user_agents) if use_user_agent else None
                    valid_proxies = validate_proxy_and_user_agent(proxy, user_agent, f"https://www.google.com/search?q=site:{url}", proxy_mode)
                    if valid_proxies:
                        current_proxy = proxy
                        current_user_agent = user_agent
                        click.echo(click.style(f"Using Proxy: {current_proxy}", fg="blue"))
                        if use_user_agent:
                            click.echo(click.style(f"Using User-Agent: {current_user_agent}", fg="blue"))
                        validated = True
                    else:
                        click.echo(click.style(f"Proxy {proxy} is not valid. Retrying...", fg="red"))

            status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
            click.echo(click.style(f"URL: {url}", fg="cyan"))
            click.echo(click.style(f"Indexing Status: {status}", fg="green" if status == "Indexed" else "red"))
        
        elif choice == 2:
            input_file = click.prompt(click.style("Enter the path to the input file (CSV/JSON)", fg="cyan"), type=click.Path(exists=True))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_output_file = f"index_spy_output_{timestamp}.csv"
            output_file = click.prompt(click.style("Enter the path to the output CSV file", fg="cyan"), type=click.Path(), default=default_output_file)
            data = read_input_file(input_file)
            results = []
            
            click.echo(click.style("Starting URL processing...", fg="green", bold=True))

            proxy_failure_count = 0
            captcha_failure_count = 0

            for index in tqdm(range(len(data)), desc="Processing URLs"):
                url = data.loc[index, 'url']
                if use_proxy or use_user_agent:
                    retries = 0
                    while not validated and retries < 5:
                        proxy = next(proxies) if use_proxy else None
                        user_agent = random.choice(user_agents) if use_user_agent else None
                        valid_proxies = validate_proxy_and_user_agent(proxy, user_agent, f"https://www.google.com/search?q=site:{url}", proxy_mode)
                        if valid_proxies:
                            current_proxy = proxy
                            current_user_agent = user_agent
                            click.echo(click.style(f"Using Proxy: {current_proxy}", fg="blue"))
                            if use_user_agent:
                                click.echo(click.style(f"Using User-Agent: {current_user_agent}", fg="blue"))
                            validated = True
                        else:
                            click.echo(click.style(f"Proxy {proxy} is not valid. Retrying...", fg="red"))
                            retries += 1
                    if retries >= 5:
                        click.echo(click.style("Too many retries with proxies and user agents. Saving progress and aborting...", fg="red", bold=True))
                        save_progress(results, output_file)
                        return

                status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                
                if "Captcha Encountered" in status:
                    captcha_failure_count += 1
                    if use_user_agent:
                        click.echo(click.style("Captcha encountered! Changing user agent.", fg="red"))
                        time.sleep(2)
                        current_user_agent = random.choice(user_agents)
                        click.echo(click.style(f"Using User-Agent: {current_user_agent}", fg="blue"))
                        status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                    if "Captcha Encountered" in status and use_proxy:
                        click.echo(click.style("Captcha encountered again! Changing proxy and user agent.", fg="red"))
                        time.sleep(2)
                        validated = False
                        retries = 0
                        while not validated and retries < 5:
                            proxy = next(proxies)
                            user_agent = random.choice(user_agents) if user_agents else None
                            valid_proxies = validate_proxy_and_user_agent(proxy, user_agent, f"https://www.google.com/search?q=site:{url}", proxy_mode)
                            if valid_proxies:
                                current_proxy = proxy
                                current_user_agent = user_agent
                                click.echo(click.style(f"Using Proxy: {current_proxy}", fg="blue"))
                                if use_user_agent:
                                    click.echo(click.style(f"Using User-Agent: {current_user_agent}", fg="blue"))
                                validated = True
                            else:
                                click.echo(click.style(f"Proxy {proxy} is not valid. Retrying...", fg="red"))
                                retries += 1
                            if retries >= 5:
                                click.echo(click.style("Too many retries with proxies and user agents. Saving progress and aborting...", fg="red", bold=True))
                                save_progress(results, output_file)
                                return

                        status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                    
                if captcha_failure_count >= 3 and not use_proxy:
                    click.echo(click.style("Too many captcha encounters. Waiting for 5 minutes...", fg="red"))
                    time.sleep(300)
                    captcha_failure_count = 0
                    status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                    if "Captcha Encountered" in status:
                        click.echo(click.style("Captcha issue persists. Saving progress and exiting...", fg="red"))
                        save_progress(results, output_file)
                        return

                results.append({
                    'url': url,
                    'indexing_status': status,
                    'proxy': current_proxy,
                    'user_agent': current_user_agent
                })

            save_progress(results, output_file)
        
        elif choice == 3:
            click.echo(click.style("Exiting IndexSpy. Goodbye!", fg="red", bold=True))
            break
        
        else:
            click.echo(click.style("Invalid choice. Please select a valid option.", fg="red"))

        click.echo("\n" + "="*50 + "\n")

if __name__ == "__main__":
    index_spy()

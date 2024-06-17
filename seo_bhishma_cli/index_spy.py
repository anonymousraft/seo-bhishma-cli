import requests
import pandas as pd
import click
import random
import time
from itertools import cycle
from bs4 import BeautifulSoup
from datetime import datetime
import signal
import sys
from rich.console import Console
from rich.progress import track
from rich.prompt import Prompt
from rich.progress import Progress

console = Console()

# Load user agents from a file
def load_user_agents(user_agent_file):
    try:
        with open(user_agent_file, 'r') as f:
            user_agents = f.read().splitlines()
        return user_agents
    except FileNotFoundError:
        console.print(f"[red]File not found: {user_agent_file}. Please enter a valid file path.[/red]")
        return None

# Load proxies from a file
def load_proxies(proxy_file):
    try:
        with open(proxy_file, 'r') as f:
            proxies = f.read().splitlines()
        return proxies
    except FileNotFoundError:
        console.print(f"[red]File not found: {proxy_file}. Please enter a valid file path.[/red]")
        return None

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
                console.print(f"[red]Proxy {proxy} returned 429 Too Many Requests. Applying delay...[/red]")
                time.sleep(60)  # Apply a delay if 429 is encountered
            else:
                console.print(f"[red]Proxy {proxy} returned status code {response.status_code}[/red]")
        except requests.RequestException as e:
            console.print(f"[red]Proxy {proxy} failed with error: {e}[/red]")
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
            # console.print(f"[yellow]Applying rate limit: Waiting for {rate_limit} seconds...[/yellow]")
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
    try:
        if file_path.endswith('.csv'):
            return pd.read_csv(file_path)
        elif file_path.endswith('.json'):
            return pd.read_json(file_path)
        else:
            raise ValueError("Unsupported file format. Use CSV or JSON.")
    except FileNotFoundError:
        console.print(f"[red]File not found: {file_path}. Please enter a valid file path.[/red]")
        return None

def save_progress(results, output_file):
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False)
    console.print(f"[green bold]Progress saved to {output_file}[/green bold]")

def signal_handler(sig, frame):
    console.print("[red bold]\nProcess interrupted! Saving progress...[/red bold]")
    save_progress(results, output_file)
    sys.exit(0)

@click.command()
@click.pass_context
def index_spy(ctx):
    """Check if URLs are indexed by Google."""
    global results, output_file

    use_proxy = Prompt.ask("[cyan]Do you want to use proxies?[/cyan]", default="no").lower() == "yes"
    proxy_file = None
    proxies = None
    valid_proxies = None
    current_proxy = None
    proxy_mode = ['http', 'https']
    if use_proxy:
        while True:
            proxy_file = Prompt.ask("[cyan]Enter the path to the proxy file[/cyan]")
            proxies = load_proxies(proxy_file)
            if proxies:
                proxies = cycle(proxies)
                break

        proxy_mode_choice = Prompt.ask(
            "[cyan]Select proxy mode[/cyan]",
            choices=['HTTP', 'HTTPS', 'Both', 'SOCKS4', 'SOCKS5'],
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
        
    use_user_agent = Prompt.ask("[cyan]Do you want to randomize user agents?[/cyan]", default="no").lower() == "yes"
    user_agents = None
    current_user_agent = None
    if use_user_agent:
        while True:
            user_agent_file = Prompt.ask("[cyan]Enter the path to the user agent file[/cyan]")
            user_agents = load_user_agents(user_agent_file)
            if user_agents:
                break
    
    use_captcha_service = Prompt.ask("[cyan]Do you want to use a paid captcha solving service?[/cyan]", default="no").lower() == "yes"
    captcha_service = None
    captcha_key = None
    if use_captcha_service:
        captcha_service = Prompt.ask("[cyan]Enter the captcha service (2Captcha or Anti-Captcha)[/cyan]", default='2Captcha')
        captcha_key = Prompt.ask("[cyan]Enter your captcha service API key[/cyan]")

    while True:
        try:
            rate_limit = int(Prompt.ask("[cyan]Enter the delay between requests in seconds (0 for no delay)[/cyan]", default="0"))
            break
        except ValueError:
            console.print("[red]Invalid input. Please enter a valid number.[/red]")

    validated = False
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        console.print("\n" + "="*50)
        console.print("[yellow bold]IndexSpy - Bulk Indexing Checker[/yellow bold]")
        console.print("[cyan]1. Check a single URL[/cyan]")
        console.print("[cyan]2. Check URLs from a file[/cyan]")
        console.print("[red bold]3. Exit[/red bold]")

        while True:
            try:
                choice = int(Prompt.ask("[cyan bold]Enter your choice[/cyan bold]"))
                if choice in [1, 2, 3]:
                    break
                else:
                    console.print("[red]Invalid choice. Please select a valid option.[/red]")
            except ValueError:
                console.print("[red]Invalid input. Please enter a number.[/red]")

        if choice == 1:
            url = Prompt.ask("[cyan]Enter the URL to check indexing status[/cyan]")
            if use_proxy or use_user_agent:
                while not validated:
                    proxy = next(proxies) if use_proxy else None
                    user_agent = random.choice(user_agents) if use_user_agent else None
                    valid_proxies = validate_proxy_and_user_agent(proxy, user_agent, f"https://www.google.com/search?q=site:{url}", proxy_mode)
                    if valid_proxies:
                        current_proxy = proxy
                        current_user_agent = user_agent
                        console.print(f"[blue]Using Proxy: {current_proxy}[/blue]")
                        if use_user_agent:
                            console.print(f"[blue]Using User-Agent: {current_user_agent}[/blue]")
                        validated = True
                    else:
                        console.print(f"[red]Proxy {proxy} is not valid. Retrying...[/red]")

            status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
            console.print(f"[cyan]URL: {url}[/cyan]")
            console.print(f"[green]Indexing Status: {status}[/green]" if status == "Indexed" else f"[red]Indexing Status: {status}[/red]")
        
        elif choice == 2:
            while True:
                input_file = Prompt.ask("[cyan]Enter the path to the input file (CSV/JSON)[/cyan]")
                data = read_input_file(input_file)
                if data is not None:
                    break
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_output_file = f"index_spy_output_{timestamp}.csv"
            output_file = Prompt.ask("[cyan]Enter the path to the output CSV file[/cyan]", default=default_output_file)
            results = []
            
            console.print("[green bold]Starting URL processing...[/green bold]")

            proxy_failure_count = 0
            captcha_failure_count = 0

            for index in track(range(len(data)), description="Processing URLs"):
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
                            console.print(f"[blue]Using Proxy: {current_proxy}[/blue]")
                            if use_user_agent:
                                console.print(f"[blue]Using User-Agent: {current_user_agent}[/blue]")
                            validated = True
                        else:
                            console.print(f"[red]Proxy {proxy} is not valid. Retrying...[/red]")
                            retries += 1
                    if retries >= 5:
                        console.print("[red bold]Too many retries with proxies and user agents. Saving progress and aborting...[/red bold]")
                        save_progress(results, output_file)
                        return

                status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                
                if "Captcha Encountered" in status:
                    captcha_failure_count += 1
                    if use_user_agent:
                        console.print("[red]Captcha encountered! Changing user agent.[/red]")
                        time.sleep(2)
                        current_user_agent = random.choice(user_agents)
                        console.print(f"[blue]Using User-Agent: {current_user_agent}[/blue]")
                        status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                    if "Captcha Encountered" in status and use_proxy:
                        console.print("[red]Captcha encountered again! Changing proxy and user agent.[/red]")
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
                                console.print(f"[blue]Using Proxy: {current_proxy}[/blue]")
                                if use_user_agent:
                                    console.print(f"[blue]Using User-Agent: {current_user_agent}[/blue]")
                                validated = True
                            else:
                                console.print(f"[red]Proxy {proxy} is not valid. Retrying...[/red]")
                                retries += 1
                            if retries >= 5:
                                console.print("[red bold]Too many retries with proxies and user agents. Saving progress and aborting...[/red bold]")
                                save_progress(results, output_file)
                                return

                        status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                    
                if captcha_failure_count >= 3 and not use_proxy:
                    console.print("[red]Too many captcha encounters. Waiting for 5 minutes...[/red]")
                    time.sleep(300)
                    captcha_failure_count = 0
                    status = check_indexing_status(url, valid_proxies, current_user_agent, captcha_service, captcha_key, rate_limit)
                    if "Captcha Encountered" in status:
                        console.print("[red]Captcha issue persists. Saving progress and exiting...[/red]")
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
            console.print("[red bold]Exiting IndexSpy. Goodbye![/red bold]")
            break
        
        else:
            console.print("[red]Invalid choice. Please select a valid option.[/red]")

        console.print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    index_spy()

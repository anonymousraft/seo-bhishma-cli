from seo_bhishma_cli.common import *
from itertools import cycle
from bs4 import BeautifulSoup
from requests_html import HTMLSession
from browserforge.headers import HeaderGenerator
import asyncio
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

console = Console()
session = None
driver = None

def pb_checks():
    playwright_cache_dir = Path.home() / ".cache" / "ms-playwright"
    
    if not playwright_cache_dir.exists():
        # Additional check for Windows where the cache might be stored in a different location
        playwright_cache_dir = Path.home() / "AppData" / "Local" / "ms-playwright"
    
    return playwright_cache_dir.exists() and any(playwright_cache_dir.iterdir())


def install_playwright_binaries():
    if not pb_checks():
        try:
            subprocess.run(["python", "-m", "playwright", "install", "chromium"], check=True)
            print("Chromium browser installed successfully for Playwright.")
        except Exception as e:
            console.print(f"An error occurred while installing Playwright binaries: {e}")
            exit(1)

def load_proxies(proxy_file):
    try:
        with open(proxy_file, 'r') as f:
            proxies = f.read().splitlines()
        return proxies
    except FileNotFoundError:
        console.print(f"[red][-] File not found: {proxy_file}. Please enter a valid file path.[/red]")
        return None

async def validate_proxy_playwright(proxy, url, proxy_mode, retries=3):
    async with async_playwright() as p:
        for protocol in proxy_mode:
            proxy_server = f"{protocol}://{proxy}"
            for attempt in range(retries):
                browser = None
                try:
                    console.print(f"[blue][+] Attempt {attempt + 1}: Launching browser with proxy {proxy_server}[/blue]")
                    browser = await p.chromium.launch(
                        proxy={
                            "server": proxy_server,
                            }
                        )
                    # browser = await p.chromium.launch(proxy={"server": "per-context"})
                    context = await browser.new_context()
                    page = await context.new_page()
                    console.print(f"[blue][+] Attempt {attempt + 1}: Navigating to {url}[/blue]")
                    await page.goto(url, timeout=60000)
                    content = await page.content()
                    console.print(f"[blue][+] Attempt {attempt + 1}: Page content retrieved[/blue]")

                    if "captcha" not in content.lower():
                        console.print(f"[green][+] Valid Proxy: {proxy} for Playwright on attempt {attempt + 1}[/blue]")
                        await browser.close()
                        return {protocol: proxy_server}
                    else:
                        print(f"[red][-] Proxy {proxy} returned captcha on attempt {attempt + 1}[/red]")
                        await browser.close()
                        break
                except Exception as e:
                    console.print(f"[red][-] Proxy {proxy} failed with error: {e} on attempt {attempt + 1}[/red]")
                    if "net::ERR_TUNNEL_CONNECTION_FAILED" in str(e) or "net::ERR_PROXY_CONNECTION_FAILED" in str(e):
                        console.print(f"[red][-] Proxy {proxy} encountered a tunnel or connection error on attempt {attempt + 1}. Retrying...[/red]")
                    else:
                        break
                finally:
                    if browser:
                        await context.close()
                        await browser.close()
    return None

def validate_proxy(proxy, url, proxy_mode, method_choice):
    if method_choice == 'HTMLSession':
        # Original HTMLSession-based implementation
        global session
        if session:
            session.close()
        session = HTMLSession()
        headers = generate_headers()

        for protocol in proxy_mode:
            proxies = {protocol: f"{protocol}://{proxy}"}
            try:
                response = session.get(url, headers=headers, proxies=proxies, timeout=10)
                response.html.render(timeout=20)
                if response.status_code == 200 and "captcha" not in response.text.lower():
                    console.print(f"[blue][+] Valid Proxy: {proxy}[/blue]")
                    return proxies
                elif response.status_code == 429:
                    console.print(f"[red][-] Proxy {proxy} returned 429 Too Many Requests. Applying delay...[/red]")
                    time.sleep(60)
                else:
                    console.print(f"[-] [red]Proxy {proxy} returned status code {response.status_code}[/red]")
            except requests.RequestException as e:
                console.print(f"[red][-] Proxy {proxy} failed with error: {e}[/red]")
    else:
        return asyncio.run(validate_proxy_playwright(proxy, url, proxy_mode))


def proxy_generator(proxies):
    for proxy in cycle(proxies):
        yield proxy

def proxy_validation_check(proxy_gen, proxy_mode, method_choice, start_index=0):
    query = "https://www.google.com/"
    for _ in range(start_index):
        next(proxy_gen)

    try:
        while True:
            proxy = next(proxy_gen)
            valid_proxies = validate_proxy(proxy, query, proxy_mode, method_choice)
            if valid_proxies:
                return True, valid_proxies, proxy_gen
            else:
                console.print(f"[red][-] Proxy {proxy} is not valid. Retrying...[/red]")
    except StopIteration:
        return False, None, proxy_gen

def generate_headers():
    headers_object = HeaderGenerator(
        browser=('chrome', 'firefox', 'safari', 'edge'),
        os=('windows', 'macos', 'linux', 'android', 'ios'),
        device=('desktop', 'mobile'),
        locale=('en-US', 'en', 'de'),
        http_version=2
    )
    headers = headers_object.generate()
    return headers

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
        raise Exception("[-] Failed to send captcha solving request")

    response_text = response.text.split('|')
    if response_text[0] != 'OK':
        raise Exception(f"[-] Error from 2Captcha: {response.text}")
    
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
            raise Exception(f"[-] Error solving captcha: {solution_response.text}")

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
        raise Exception("[-] Failed to send captcha solving request")

    response_json = response.json()
    if response_json.get('errorId') != 0:
        raise Exception(f"[-] Error from Anti-Captcha: {response_json.get('errorDescription')}")

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
            raise Exception(f"[-] Error solving captcha: {result.get('errorDescription')}")

def solve_captcha(captcha_service, captcha_key, url, site_key):
    if captcha_service.lower() == '2captcha':
        return solve_captcha_2captcha(captcha_key, url, site_key)
    elif captcha_service.lower() == 'anti-captcha':
        return solve_captcha_anticaptcha(captcha_key, url, site_key)
    return None

def check_indexing_status_htmlsession(url, proxies=None, captcha_service=None, captcha_key=None, rate_limit=0):
    global session
    if session is None:
        session = HTMLSession()

    query = f"site:{url}"
    headers = generate_headers()
    search_url = f"https://www.google.com/search?q={query}"

    try:
        response = session.get(search_url, headers=headers, proxies=proxies, timeout=10)
        response.html.render(timeout=20)

        if "captcha" in response.text.lower():
            if captcha_service and captcha_key:
                site_key = get_site_key(search_url)
                if site_key:
                    captcha_solution = solve_captcha(captcha_service, captcha_key, search_url, site_key)
                    if captcha_solution:
                        headers['g-recaptcha-response'] = captcha_solution
                        response = session.get(search_url, headers=headers, proxies=proxies, timeout=10)
                        response.html.render(timeout=20)
                        if "captcha" not in response.text.lower():
                            return parse_indexing_status(response, url)
            return "Captcha Encountered"

        return parse_indexing_status(response, url)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return f"Error: {e}"
    finally:
        if rate_limit > 0:
            time.sleep(rate_limit)

def parse_indexing_status(response, url):
    soup = BeautifulSoup(response.html.html, 'html.parser')
    
    no_results_message = soup.find("p", role="heading")
    if no_results_message and "did not match any documents" in no_results_message.text.lower():
        return "Not Indexed"
    
    search_results = soup.find_all('div', class_='g')
    if search_results:
        for result in search_results:
            link = result.find('a', href=True)
            if link and url in link['href']:
                return "Indexed"
    
    return "Not Indexed"

async def check_indexing_status_playwright(url, proxy=None, captcha_handling_choice=None, headless=False):
    async with async_playwright() as p:
        browser_options = {
            "headless": headless,
            "args": [
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--log-level=3"
            ]
        }
        
        if proxy:
            browser_options["proxy"] = {
                "server": proxy['http'] if 'http' in proxy else proxy['https']
            }

        browser = await p.chromium.launch(**browser_options)
        page = await browser.new_page()

        try:
            search_url = f"https://www.google.com/search?q=site:{url}"
            await page.goto(search_url)
            await page.wait_for_timeout(5000)  # Wait for 5 seconds

            page_content = await page.content()
            if "captcha" in page_content.lower():
                if not headless and captcha_handling_choice == 'By user':
                    print("[yellow][-] Captcha encountered! Please solve the captcha in the browser window.[/yellow]")
                    while "captcha" in await page.content().lower():
                        try:
                            await page.wait_for_timeout(5000)
                        except:
                            await browser.close()
                            return None
                    return await check_indexing_status_playwright(url, proxy, captcha_handling_choice, headless)
                else:
                    print("[yellow][-] Captcha encountered! Waiting for 60 seconds...[/yellow]")
                    await page.wait_for_timeout(60000)
                    return "Captcha Encountered"

            soup = BeautifulSoup(page_content, 'html.parser')
            no_results_message = soup.find("p", role="heading")
            if no_results_message and "did not match any documents" in no_results_message.text.lower():
                return "Not Indexed"

            search_results = soup.find_all('div', class_='g')
            for result in search_results:
                link = result.find('a', href=True)
                if link and url in link['href']:
                    return "Indexed"

            return "Not Indexed"
        except Exception as e:
            if "net::ERR_TUNNEL_CONNECTION_FAILED" in str(e):
                print(f"[red]Playwright Error: {e} - Changing Proxy[/red]")
                return "Proxy Error"
            else:
                print(f"[red]Playwright Error: {e}[/red]")
                return f"Error: {e}"
        finally:
            await browser.close()
            

def read_input_file(file_path):
    try:
        if file_path.endswith('.csv'):
            return pd.read_csv(file_path)
        elif file_path.endswith('.json'):
            return pd.read_json(file_path)
        else:
            raise ValueError("[-] Unsupported file format. Use CSV or JSON.")
    except FileNotFoundError:
        console.print(f"[red][-] File not found: {file_path}. Please enter a valid file path.[/red]")
        return None

def save_progress(results, output_file):
    df = pd.DataFrame(results)
    df.to_csv(output_file, index=False, encoding='utf-8')
    console.print(f"[green bold][+] Progress saved to {output_file}[/green bold]")

def signal_handler(sig, frame):
    console.print("[red bold]\n[/] Process interrupted! Saving progress...[/red bold]")
    save_progress(results, output_file)
    sys.exit(0)

def handle_browser_close():
    if driver:
        driver.quit()
    console.print("[red bold]\n[/] Browser closed! Saving progress...[/red bold]")
    save_progress(results, output_file)
    sys.exit(0)

@click.command()
@click.pass_context
def index_spy(ctx):
    """Check indexing for bulk URLs"""
    global results, output_file, driver

    use_proxy = Prompt.ask("[cyan]Do you want to use proxies?[/cyan]", default="no").lower() == "yes"
    proxy_file = None
    proxies = None
    valid_proxies = None
    current_proxy = None
    proxy_mode = ['http', 'https']
    
    if use_proxy:
        proxy_file = Prompt.ask("[cyan]Enter the path to the proxy file[/cyan]")
        proxies = load_proxies(proxy_file)

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
            console.print("[red][-] Invalid input. Please enter a valid number.[/red]")

    validated = False
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, handle_browser_close)

    while True:
        console.print(Panel("Welcome to IndexSpy\nBulk Indexing Checker with Proxy & Selenium", title="IndexSpy", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))
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
            valid_proxies = None

            if use_proxy:
                proxy_gen = proxy_generator(proxies)
                while True:
                    validated, validated_proxies, proxy_gen = proxy_validation_check(proxy_gen, proxy_mode, 'HTMLSession')
                    if validated and validated_proxies:
                        valid_proxies = validated_proxies
                        console.print(f"[blue][+] Using Proxy: {validated_proxies}[/blue]")
                        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                            task = progress.add_task("Checking indexing status...", total=None)
                            status = check_indexing_status_htmlsession(url, valid_proxies, captcha_service, captcha_key, rate_limit)
                            progress.update(task, completed=True)
                        if 'Captcha' in status:
                            console.print(f"[red][-] Captcha Encountered, Changing Proxy[/red]")
                        else:
                            break
                    else:
                        console.print(f"[red][-] All the proxies are not valid, Try with Others..[/red]")
                        exit()
            else:
                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                    task = progress.add_task("Checking indexing status...", total=None)
                    status = check_indexing_status_htmlsession(url, valid_proxies, captcha_service, captcha_key, rate_limit)
                    progress.update(task, completed=True)

            console.print(f"[cyan]\n[+] URL: {url}[/cyan]")
            console.print(f"[green][+] Indexing Status: {status}[/green]" if status == "Indexed" else f"[red][-] Indexing Status: {status}[/red]")
        
        elif choice == 2:
            while True:
                input_file = Prompt.ask("[cyan]Enter the path to the input file (CSV/JSON)[/cyan]")
                data = read_input_file(input_file)
                if data is not None:
                    break
            
            method_choice = Prompt.ask(
                "[cyan]Select checking method[/cyan]",
                choices=['HTMLSession', 'Selenium'],
                default='HTMLSession'
            )

            headless = False
            if method_choice == 'Selenium':
                install_playwright_binaries()
                headless = Prompt.ask("[cyan]Do you want to run Selenium in headless mode?[/cyan]", default="no").lower() == "yes"

            captcha_handling_choice = None
            if method_choice == 'Selenium' and not headless:
                captcha_handling_choice = Prompt.ask(
                    "[cyan]How do you want to handle captchas?[/cyan]",
                    choices=['By user', 'Automatic'],
                    default='By user'
                )

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_output_file = f"index_spy_output_{timestamp}.csv"
            output_file = Prompt.ask("[cyan]Enter the path to the output CSV file[/cyan]", default=default_output_file)
            results = []
            
            console.print("[green bold][+] Starting URL processing...[/green bold]")

            proxy_failure_count = 0
            captcha_failure_count = 0

            validated = False
            proxy_gen = proxy_generator(proxies) if use_proxy else None
            start_index = 0
            processed_count = 0

            if use_proxy:
                validated, valid_proxies, proxy_gen = proxy_validation_check(proxy_gen, proxy_mode, method_choice, start_index)
                if not validated:
                    console.print(f"[red][-] All proxies are invalid. Switching to no proxy mode.[/red]")
                    use_proxy = False

            for index in track(range(len(data)), description="[+] Processing URLs"):
                url = data.loc[index, 'url']
                if use_proxy:
                    if processed_count % 20 == 0 or processed_count == 0:
                        console.print(f"[blue][+] Using Proxy: {valid_proxies}[/blue]")
                    
                    if method_choice == 'HTMLSession':
                        status = check_indexing_status_htmlsession(url, valid_proxies, captcha_service, captcha_key, rate_limit)
                    else:
                        # status = check_indexing_status_selenium(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless)
                        status = asyncio.run(check_indexing_status_playwright(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless))
                        if status == "Proxy Error":
                            validated = False
                            while not validated:
                                validated, valid_proxies, proxy_gen = proxy_validation_check(proxy_gen, proxy_mode, method_choice, start_index)
                                if validated:
                                    console.print(f"[blue][+] Using Proxy: {valid_proxies}[/blue]")
                                    status = asyncio.run(check_indexing_status_playwright(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless))
                                    #status = check_indexing_status_selenium(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless)
                                    if "Captcha Encountered" not in status and "Proxy Error" not in status:
                                        break

                else:
                    if method_choice == 'HTMLSession':
                        status = check_indexing_status_htmlsession(url, None, captcha_service, captcha_key, 10)
                    else:
                        #status = check_indexing_status_selenium(url, captcha_handling_choice=captcha_handling_choice, headless=headless)
                        status = asyncio.run(check_indexing_status_playwright(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless))

                if "Captcha Encountered" in status:
                    if use_proxy and not (method_choice == 'Selenium' and captcha_handling_choice == 'By user'):
                        captcha_failure_count += 1
                        console.print("[red][-] Captcha encountered! Changing proxy.[/red]")
                        start_index = index
                        validated = False
                        while not validated:
                            validated, valid_proxies, proxy_gen = proxy_validation_check(proxy_gen, proxy_mode, method_choice, start_index)
                            if validated:
                                console.print(f"[blue][+] Using Proxy: {valid_proxies}[/blue]")
                                if method_choice == 'HTMLSession':
                                    status = check_indexing_status_htmlsession(url, valid_proxies, captcha_service, captcha_key, rate_limit)
                                else:
                                    # status = check_indexing_status_selenium(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless)
                                    status = asyncio.run(check_indexing_status_playwright(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless))
                                if "Captcha Encountered" not in status and "Proxy Error" not in status:
                                    break
                        if not validated:
                            console.print("[red][-] Too many retries with proxies. Switching to no proxy mode.[/red]")
                            use_proxy = False
                            if method_choice == 'HTMLSession':
                                status = check_indexing_status_htmlsession(url, None, captcha_service, captcha_key, 10)
                            else:
                                # status = check_indexing_status_selenium(url, captcha_handling_choice=captcha_handling_choice, headless=headless)
                                status = asyncio.run(check_indexing_status_playwright(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless))
                            if "Captcha Encountered" in status:
                                console.print("[red][-] Captcha issue persists. Saving progress and exiting...[/red]")
                                save_progress(results, output_file)
                                return
                    else:
                        captcha_failure_count += 1
                        if method_choice == 'HTMLSession' or (method_choice == 'Selenium' and captcha_handling_choice == 'Automatic'):
                            console.print("[red][-] Captcha encountered! Applying Sleep for 20 seconds[/red]")
                            time.sleep(20)
                            if method_choice == 'HTMLSession':
                                status = check_indexing_status_htmlsession(url, None, captcha_service, captcha_key, 10)
                            else:
                                # status = check_indexing_status_selenium(url, captcha_handling_choice=captcha_handling_choice, headless=headless)
                                status = asyncio.run(check_indexing_status_playwright(url, valid_proxies, captcha_handling_choice=captcha_handling_choice, headless=headless))

                if captcha_failure_count >= 3 and not use_proxy and not (method_choice == 'Selenium' and captcha_handling_choice == 'By user'):
                    console.print("[red][-] Too many captcha encounters. Saving progress and exiting...[/red]")
                    save_progress(results, output_file)
                    return

                if "Captcha Encountered" not in status and "Proxy Error" not in status:
                    results.append({
                        'url': url,
                        'indexing_status': status,
                        'proxy': current_proxy if use_proxy else "No Proxy"
                    })
                    processed_count += 1

                    if processed_count % 20 == 0:
                        save_progress(results, output_file)
                else:
                    console.print("[yellow][-] Captcha encountered! Retrying...[/yellow]")
                    index -= 1

            save_progress(results, output_file)
        
        elif choice == 3:
            console.print("[red bold]Exiting IndexSpy. Goodbye![/red bold]")
            break
        
        else:
            console.print("[red][-] Invalid choice. Please select a valid option.[/red]")

        console.print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    index_spy()

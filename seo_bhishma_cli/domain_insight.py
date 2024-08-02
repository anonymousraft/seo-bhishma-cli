import os
import requests
import gzip
import pandas as pd
import socket
import requests
import dns.resolver
import whois
import click
import datetime
import time
import re
import sublist3r
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from ipwhois import IPWhois
from geopy.geocoders import Nominatim
from fake_useragent import UserAgent
from rich.console import Console
from rich.panel import Panel
from seo_bhishma_cli.constants import CLI_NAME, CLI_VERSION, CLI_AUTHOR
from rich.progress import Progress, SpinnerColumn, TextColumn, track
from Wappalyzer import Wappalyzer, WebPage
from requests_html import HTMLSession
from browserforge.headers import HeaderGenerator
from tempfile import NamedTemporaryFile
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
import subprocess

# Initialize rich console
console = Console()
geolocator = Nominatim(user_agent="domain_insight")
session = None
driver = None

ua = UserAgent()

def pb_checks():
    playwright_cache_dir = Path.home() / ".cache" / "ms-playwright"
    
    if not playwright_cache_dir.exists():
        # Additional check for Windows where the cache might be stored in a different location
        playwright_cache_dir = Path.home() / "AppData" / "Local" / "ms-playwright"
    
    return playwright_cache_dir.exists() and any(playwright_cache_dir.iterdir())


def install_playwright_binaries():
    if not pb_checks():
        try:
            subprocess.run(["playwright", "install"], check=True)
            print("Playwright binaries installed successfully.")
        except Exception as e:
            print(f"An error occurred while installing Playwright binaries: {e}")
            exit(1)

# Global variable to store the domain for the session
current_domain = None

def generate_headers():
    headers_object = HeaderGenerator(
        browser=('chrome', 'firefox', 'safari', 'edge'),
        os=('windows', 'macos', 'linux', 'android', 'ios'),
        device=('desktop', 'mobile'),
        locale=('en-US', 'en', 'in'),
        http_version=2
        )
    headers = headers_object.generate()
    return headers

def is_valid_domain_or_url(input_string):
    domain_regex = re.compile(
        r'^(?:http[s]?://)?(?:www\.)?'
        r'(?P<domain>[a-zA-Z0-9-]{1,63}\.(?:[a-zA-Z]{2,}|[a-zA-Z]{2,3}\.[a-zA-Z]{2,3}))'
        r'(?::\d{1,5})?(?:[/?#]\S*)?$'
    )
    match = domain_regex.match(input_string)
    return match is not None

def extract_domain(url):
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc if parsed_url.netloc else parsed_url.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception as e:
        console.log(f"[bold red][-] Error extracting domain from URL: {e}[/bold red]")
        return None

def set_domain():
    global current_domain
    while True:
        user_input = click.prompt(click.style("Enter the domain name or URL", fg="cyan", bold=True))
        if is_valid_domain_or_url(user_input):
            current_domain = extract_domain(user_input)
            break
        else:
            console.print("[bold red][-] Invalid domain or URL. Please try again.[/bold red]")

def get_ip_address(domain):
    try:
        return socket.gethostbyname(domain)
    except Exception as e:
        console.log(f"[bold red][-] Error retrieving IP address for {domain}: {e}[/bold red]")
        return None

# REVERSE IP STATRS
def parse_page(page_source):
    soup = BeautifulSoup(page_source, 'html.parser')
    h1_title = soup.find('h1').get_text() if soup.find('h1') else 'No title found'
    table = soup.find('table')
    table_info = {}

    if table:
        table_rows = table.find_all('tr')
        for row in table_rows:
            cols = row.find_all('td')
            if len(cols) >= 2:
                key = cols[0].get_text().strip()
                value = cols[1].get_text().strip()
                table_info[key] = value
    else:
        console.log("[bold red]No table found on the page[/bold red]")
        return None, None, None  # Return None if the table is not found

    textarea = soup.find('textarea')
    domains_list = textarea.get_text().strip().split('\n') if textarea else []

    return h1_title, table_info, domains_list

def save_reverse_ip_results(domain, h1_title, table_info, domains_list):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{domain}_reverse_ip_{timestamp}.txt"
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(f"Title: {h1_title}\n\n")
        file.write("Table Information:\n")
        for key, value in table_info.items():
            file.write(f"{key}: {value}\n")
        file.write("\nDomains List:\n")
        for domain in domains_list:
            file.write(f"{domain}\n")
    return output_file

async def scrape_with_playwright(ip):
    query = f"https://domains.tntcode.com/ip/{ip}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto(query)

        # Loop until CAPTCHA is solved and the table is found or another condition is met
        while True:
            if "Captcha" in await page.title():
                print("CAPTCHA detected. Please solve the CAPTCHA in the browser.")
                while "Captcha" in await page.title():
                    try:
                        await page.wait_for_selector("body", timeout=10000)
                    except Exception:
                        print("Browser window closed by the user.")
                        await browser.close()
                        return None
            try:
                await page.wait_for_selector("table", timeout=20000)
                break
            except Exception:
                print("Waiting for CAPTCHA to be solved or for the content to be available...")
                page_source = await page.content()
                if "not found" in page_source.lower():
                    print("Content not found")
                    await browser.close()
                    return page_source
                if "verifying you are human" not in page_source.lower():
                    break
                # Wait a bit before trying again
                await page.wait_for_selector("body", timeout=20000)

        page_source = await page.content()
        await browser.close()
        return page_source
    
def reverse_ip_lookup(ip, domain):
    try:
        console.log("[bold green]Starting reverse IP lookup...[/bold green]")
        page_source = asyncio.run(scrape_with_playwright(ip))

        if page_source is None or "not found" in page_source.lower():
            console.log("[bold red]Content not found on the page[/bold red]")
            return None, None, None, None

        h1_title, table_info, domains_list = parse_page(page_source)
        if h1_title is None or table_info is None or domains_list is None:
            console.log("[bold red]Reverse IP lookup failed. No table found on the page.[/bold red]")
            return None, None, None, None

        output_file = save_reverse_ip_results(domain, h1_title, table_info, domains_list)

        console.log("[bold green]Reverse IP lookup completed successfully.[/bold green]")
        return h1_title, table_info, domains_list, output_file
    except Exception as e:
        console.log(f"[bold red]Error performing reverse IP lookup: {e}[/bold red]")
        return None, None, None, None
    
# REVERSE IP ENDS

def find_subdomains(domain):
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{domain}_subdomains_{timestamp}.txt"
        sub_domains = sublist3r.main(domain, 40, output_file, ports= None, silent=False, verbose= False, enable_bruteforce= False, engines=None)
        return sub_domains
    except Exception as e:
        console.log(f"[bold red][-] Error finding subdomains: {e}[/bold red]")
        return None

def get_dns_records(domain):
    try:
        records = {}
        resolver = dns.resolver.Resolver()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{domain}_dns_records_{timestamp}.txt"
        with open(output_file, 'w', encoding='utf-8') as file:
            for record_type in ['A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME']:
                try:
                    answers = resolver.resolve(domain, record_type)
                    records[record_type] = [str(answer) for answer in answers]
                    file.write(f"{record_type}: {', '.join(records[record_type])}\n")
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                    records[record_type] = []
                    file.write(f"{record_type}: No record found\n")
        return records, output_file
    except Exception as e:
        console.log(f"[bold red][-] Error retrieving DNS records: {e}[/bold red]")
        return {}, None

# ROBOTS TESTING
async def fetch_robots_txt_with_playwright(domain):
    robots_urls = [
        f"https://{domain}/robots.txt",
        f"http://{domain}/robots.txt",
        f"https://www.{domain}/robots.txt",
        f"http://www.{domain}/robots.txt"
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for url in robots_urls:
            try:
                await page.goto(url)
                await page.wait_for_selector("pre", timeout=10000)
                robots_txt = await page.query_selector("pre")
                robots_txt = await robots_txt.inner_text() if robots_txt else None
                if robots_txt:
                    console.print(f"[bold green][+] Found robots.txt at {url}[/bold green]")
                    await browser.close()
                    return robots_txt
            except Exception as e:
                console.print(f"[bold red][-] Error fetching robots.txt from {url} using Playwright: {e}[/bold red]")
        
        await browser.close()
    return None

def parse_robots_txt(robots_txt):
    disallows = []
    sitemaps = []
    for line in robots_txt.splitlines():
        if line.startswith('Disallow'):
            disallows.append(line.split(': ')[1])
        elif line.startswith('Sitemap'):
            sitemaps.append(line.split(': ')[1])
    return disallows, sitemaps

def download_sitemap(sitemap_url, retries=3, delay=5):
    attempt = 0
    while attempt < retries:
        try:
            console.log(f"[bold blue][*] Downloading sitemap from {sitemap_url} (Attempt {attempt + 1})[/bold blue]")
            response = requests.get(sitemap_url, headers=generate_headers(), timeout=10)
            if response.status_code == 200:
                with NamedTemporaryFile(delete=False, suffix='.xml' if not sitemap_url.endswith('.gz') else '.xml.gz') as temp_file:
                    temp_file.write(response.content)
                    temp_file_path = temp_file.name
                return temp_file_path
            else:
                console.log(f"[bold yellow][!] Failed to download sitemap: {sitemap_url} (status code: {response.status_code})[/bold yellow]")
        except Exception as e:
            console.log(f"[bold red][-] Error downloading sitemap from {sitemap_url}: {e}[/bold red]")
        attempt += 1
        time.sleep(delay)
    return None

def extract_urls_from_sitemap(sitemap_url, sitemap_path):
    urls = []
    try:
        console.log(f"[bold blue][*] Extracting URLs from {sitemap_path}[/bold blue]")
        with open(sitemap_path, 'rb') as file:
            content = file.read()
            if sitemap_path.endswith('.gz'):
                content = gzip.decompress(content)
            soup = BeautifulSoup(content, 'xml')
            if soup.find('sitemapindex'):
                console.log(f"[bold blue][*] Sitemap index found in {sitemap_url}[/bold blue]")
                for sitemap in soup.find_all('sitemap'):
                    loc = sitemap.find('loc').text
                    temp_sitemap_path = download_sitemap(loc)
                    if temp_sitemap_path:
                        urls.extend(extract_urls_from_sitemap(loc, temp_sitemap_path))
                        os.remove(temp_sitemap_path)
            else:
                for url in soup.find_all('loc'):
                    urls.append((sitemap_url, url.text))
    except Exception as e:
        console.log(f"[bold red][-] Error extracting URLs from {sitemap_path}: {e}[/bold red]")
    console.log(f"[bold green][+] Extracted {len(urls)} URLs from {sitemap_url}[/bold green]")
    return urls

def get_sitemap_urls(domain):
    # robots_txt = fetch_robots_txt_with_selenium(domain)
    # if robots_txt:
    #     disallows, sitemaps = parse_robots_txt(robots_txt)
    #     if sitemaps:
    #         return disallows, sitemaps
    # Prompt user for sitemap URL if not found
    sitemap_url = console.input(f"[bold yellow][?] No sitemap URL found in robots.txt. Please provide the sitemap URL for {domain}: [/bold yellow]")
    return sitemap_url

def check_urls_against_robots(disallows, urls):
    results = []
    total_urls = len(urls)
    total_rules = len(disallows)
    console.log(f"[bold blue][*] Checking {total_urls} URLs against {total_rules} disallow rules[/bold blue]")
    blocked_count = 0

    for sitemap_url, url in track(urls, description="Checking URLs against robots.txt..."):
        url_blocked = False
        for rule in disallows:
            if rule != '/' and url.startswith(rule):
                results.append((sitemap_url, url, rule, 'Blocked'))
                url_blocked = True
                blocked_count += 1
                break
        if not url_blocked:
            results.append((sitemap_url, url, '', 'Not Blocked'))

    if blocked_count == 0:
        console.log("[bold green][+] robots.txt is not blocking any important pages[/bold green]")
    else:
        console.log(f"[bold red][-] robots.txt is blocking {blocked_count} URLs[/bold red]")

    return results, blocked_count

def save_to_csv(results, domain):
    df = pd.DataFrame(results, columns=['sitemap_url', 'url', 'robots_txt_rule', 'remark'])
    output_file = f"{domain}_robots_check.csv"
    df.to_csv(output_file, index=False)
    console.log(f"[bold green][+] Results saved to {output_file}[/bold green]")


# ROBOTS TESTING END

def format_whois_info(info):
    formatted_info = {}
    for key, value in info.items():
        if isinstance(value, list):
            value = ', '.join(str(v) for v in value)
        elif isinstance(value, datetime.datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        formatted_info[key] = value
    return formatted_info

def get_whois_info(domain):
    try:
        domain_without_sub = extract_domain(f"https://{domain}")
        info = whois.whois(domain_without_sub)
        formatted_info = format_whois_info(info)
        # Save the WHOIS information to a file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{domain_without_sub}_whois_{timestamp}.txt"
        with open(output_file, 'w', encoding='utf-8') as file:
            for key, value in formatted_info.items():
                file.write(f"{key}: {value}\n")
        return formatted_info, output_file
    except Exception as e:
        console.log(f"[bold red][-] Error retrieving WHOIS information: {e}[/bold red]")
        return {}, None

def get_ip_details(ip, domain):
    ip_info = {}

    try:
        # Get ASN information from IPWhois
        obj = IPWhois(ip)
        results = obj.lookup_rdap()
        ip_info.update({
            'ASN': results.get('asn'),
            'ASN Country Code': results.get('asn_country_code'),
            'ASN Date': results.get('asn_date'),
            'ASN Description': results.get('asn_description'),
            'ASN CIDR': results.get('asn_cidr'),
            'ASN Registry': results.get('asn_registry')
        })

    except Exception as e:
        console.log(f"[bold red][-] Error retrieving ASN details: {e}[/bold red]")

    try:
        # Get additional IP information from ipinfo.io
        response = requests.get(f"https://ipinfo.io/{ip}/json")
        if response.status_code == 200:
            data = response.json()
            ip_info.update({
                'IP': data.get('ip'),
                'Hostname': data.get('hostname'),
                'City': data.get('city'),
                'Region': data.get('region'),
                'Country': data.get('country'),
                'Location': data.get('loc'),
                'Organization': data.get('org'),
                'Postal': data.get('postal'),
                'Timezone': data.get('timezone')
            })

    except Exception as e:
        console.log(f"[bold red][-] Error retrieving ipinfo.io details: {e}[/bold red]")

    # Save the IP information to a file with UTF-8 encoding
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{domain}_ip_info_{timestamp}.txt"
        with open(output_file, 'w', encoding='utf-8') as file:
            for key, value in ip_info.items():
                file.write(f"{key}: {value}\n")

        return ip_info, output_file
    except Exception as e:
        console.log(f"[bold red][-] Error saving IP details to file: {e}[/bold red]")
        return ip_info, None

def display_results(results):
    for result in results:
        console.log(result)

def tech_analysis(domain):

     # Validate URLs
    valid_url = f"https://{domain}"

    # Create a Wappalyzer instance
    wappalyzer = Wappalyzer.latest()

    # Create a WebPage instance from the valid URL
    console.print(f"[+] Analyzing website: {valid_url}", style="bold cyan")
    webpage = WebPage.new_from_url(valid_url)

    # Analyze the webpage and get the detected technologies
    console.print("[+] Detecting technologies...", style="bold cyan")
    technologies = wappalyzer.analyze(webpage)

    # Generate timestamp and domain name
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    domain_name = urlparse(valid_url).netloc
    
    # Create output filename
    filename = f"{domain_name}_tech_lookup_{timestamp}.txt"

    # Save the results to a file
    console.print(f"[+] Saving results to {filename}", style="bold cyan")
    with open(filename, "w") as file:
        file.write(f"Analysis of {valid_url} on {timestamp}\n\n")
        for tech in technologies:
            file.write(f"{tech}\n")

    # Print the detected technologies in the console using rich
    console.print(f"[+] Technologies detected for {valid_url}:", style="bold yellow")
    for tech in technologies:
        console.print(f"[+] {tech}", style="yellow")

    console.print(f"[bold green][+] Analysis saved to {filename}[/bold green]")

@click.command()
@click.option('--domain', default=None, help='Domain to analyze')
@click.option('--choice', type=click.Choice(['1', '2', '3', '4', '5', '6', '7', '0']), default=None, help='Menu choice')
def domain_insight(domain, choice):
    """Advanced domain information gathering tool."""
    global current_domain
    current_domain = domain
    
    console.print(Panel("Welcome to Domain Insight\nPowerful domain information gathering tool.", title="Domain Insight", border_style="green", subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}", subtitle_align="right"))
    install_playwright_binaries()

    while True:

        if not current_domain:
            current_domain = click.prompt(click.style("Enter the domain to analyze", fg="cyan", bold=True))

        console.print(f"[cyan]\nCurrent domain: {current_domain}[/cyan]")
        if not choice:
            console.print("[yellow]1. Check other websites hosted on the same IP[/yellow]")
            console.print("[yellow]2. Identify subdomains[/yellow]")
            console.print("[yellow]3. Check DNS records[/yellow]")
            console.print("[yellow]4. Check robots.txt[/yellow]")
            console.print("[yellow]5. Check WHOIS record[/yellow]")
            console.print("[yellow]6. Get IP address details[/yellow]")
            console.print("[yellow]7. Tech stack analysis[/yellow]")
            console.print("[red]0. Exit[/red]")
            console.print()
            choice = click.prompt(click.style("Please choose an option", fg="yellow", bold=True), type=int)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            if choice == 1:
                task = progress.add_task("Checking IP address and other websites...", total=None)
                ip = get_ip_address(current_domain)
                h1_title, table_info, domains_list, output_file = reverse_ip_lookup(ip, current_domain) if ip else (None, None, None, None)
                progress.update(task, completed=True)
                if h1_title and table_info and domains_list:
                    console.print(f"[bold green][+] {h1_title}[/bold green]")
                    console.print(f"[bold][+] IP Info:[/bold]")
                    for key, value in table_info.items():
                        console.print(f"{key}: {value}")
                    console.print(f"[bold][+] Domains List:[/bold]")
                    for domain in domains_list:
                        console.print(f"[+] {domain}")
                    console.print(f"[bold green][+] Results saved to {output_file}[/bold green]")
                else:
                    console.print(f"[bold red][-] Failed to retrieve reverse IP lookup information.[/bold red]")
            elif choice == 2:
                subdomains = find_subdomains(current_domain)
            elif choice == 3:
                task = progress.add_task("Checking DNS records...", total=None)
                dns_records, output_file = get_dns_records(current_domain)
                progress.update(task, completed=True)
                console.print(f"[+] DNS records saved to {output_file}")
                display_results([f"{record_type}: {', '.join(records)}" for record_type, records in dns_records.items()])
            elif choice == 4:
                task_fetch_robots = progress.add_task("Checking robots.txt...", total=None)
                robots_txt = asyncio.run(fetch_robots_txt_with_playwright(current_domain))
                progress.update(task_fetch_robots, completed=True)

                if robots_txt:
                    disallows, sitemaps = parse_robots_txt(robots_txt)
                    console.print(f"[bold green][+] Disallowed rules in robots.txt: {disallows}[/bold green]")
                else:
                    console.print("[bold red][-] robots.txt not found on any of the checked URLs.[/bold red]")
                    return
                
                if not disallows:
                    console.print("[bold green][-] No disallow directive found in the robots.txt[/bold green]")
                    return

                if not sitemaps:
                    sitemap_url = get_sitemap_urls(current_domain)
                    sitemaps = [sitemap_url]

                all_urls = []
                task_fetch_sitemaps = progress.add_task("Fetching sitemap URLs...", total=None)
                for sitemap_url in track(sitemaps, description="Fetching sitemap URLs..."):
                    temp_sitemap_path = download_sitemap(sitemap_url)
                    if temp_sitemap_path:
                        urls_from_sitemap = extract_urls_from_sitemap(sitemap_url, temp_sitemap_path)
                        all_urls.extend(urls_from_sitemap)
                        os.remove(temp_sitemap_path)
                        console.print(f"[bold blue][*] {len(urls_from_sitemap)} URLs extracted from {sitemap_url}[/bold blue]")
                progress.update(task_fetch_sitemaps, completed=True)
                
                results, blocked_count = check_urls_against_robots(disallows, all_urls)

                if blocked_count > 0:
                    save_to_csv(results, current_domain)
                else:
                    console.print("[bold green][+] No URLs are blocked[/bold green]")

            elif choice == 5:
                task = progress.add_task("Checking WHOIS record...", total=None)
                whois_info, output_file = get_whois_info(current_domain)
                progress.update(task, completed=True)
                if whois_info:
                    display_results([f"{key}: {value}" for key, value in whois_info.items()])
                    console.print(f"[bold green][+] WHOIS results saved to {output_file}[/bold green]")
                else:
                    console.print(f"[bold red][-] Failed to retrieve WHOIS information.[/bold red]")
            elif choice == 6:
                task = progress.add_task("Getting IP address details...", total=None)
                ip = get_ip_address(current_domain)
                ip_details, output_file = get_ip_details(ip, current_domain) if ip else ({}, None)
                progress.update(task, completed=True)
                display_results([f"{key}: {value}" for key, value in ip_details.items()])
                if output_file:
                    console.print(f"[bold green][+] IP details saved to {output_file}[/bold green]")
            elif choice == 7:
                tech_analysis(current_domain)
            elif choice == 0:
                current_domain = False
                console.print("[bold red]Thank you for using Domain Insight![/bold red]")
                break
            else:
                console.print("[bold red][-] Invalid choice! Please try again.[/bold red]")

        choice = None

if __name__ == "__main__":
    domain_insight()
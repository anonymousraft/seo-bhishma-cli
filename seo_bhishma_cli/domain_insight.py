import socket
import requests
import dns.resolver
import whois
import click
import datetime
import re
import sublist3r
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from ipwhois import IPWhois
from geopy.geocoders import Nominatim
from fake_useragent import UserAgent
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from Wappalyzer import Wappalyzer, WebPage
from requests_html import HTMLSession
from browserforge.headers import HeaderGenerator
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException

# Initialize rich console
console = Console()
geolocator = Nominatim(user_agent="domain_insight")
session = None

ua = UserAgent()

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

def scrape_with_selenium(ip):
    options = webdriver.ChromeOptions()
    # Do not add headless option to see the browser and solve CAPTCHA manually
    options.add_argument("--disable-gpu")  # Disable GPU acceleration
    
    # Use ChromeDriverManager to get the path to the ChromeDriver
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    query = f"https://domains.tntcode.com/ip/{ip}"
    driver.get(query)

    # Loop until CAPTCHA is solved and the table is found or another condition is met
    while True:
        try:
            if driver.title == "Captcha":
                console.log("[bold yellow]CAPTCHA detected. Please solve the CAPTCHA in the browser.[/bold yellow]")
                while driver.title == "Captcha":
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )
                    except WebDriverException:
                        console.log("[bold red]Browser window closed by the user.[/bold red]")
                        driver.quit()
                        return None
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            break
        except:
            console.log("[bold yellow]Waiting for CAPTCHA to be solved or for the content to be available...[/bold yellow]")
            page_source = driver.page_source
            if "not found" in page_source.lower():
                console.log("[bold red]Content not found[/bold red]")
                driver.quit()
                return page_source
            if "verifying you are human" not in page_source.lower():
                break
            # Wait a bit before trying again
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

    page_source = driver.page_source
    driver.quit()
    return page_source

def reverse_ip_lookup(ip, domain):
    try:
        console.log("[bold green]Starting reverse IP lookup...[/bold green]")
        page_source = scrape_with_selenium(ip)

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

def check_robots_txt(domain):
    global session

    if session is None:
        session = HTMLSession()

    robots_urls = [
        f"https://{domain}/robots.txt",
        f"http://{domain}/robots.txt",
        f"https://www.{domain}/robots.txt",
        f"http://www.{domain}/robots.txt"
    ]

    disallows = []
    for url in robots_urls:
        try:
            headers = generate_headers()
            response = session.get(url, headers=headers, allow_redirects=True, timeout=10)
            if response.status_code == 200 and 'User-agent' in response.text:
                disallows = [line for line in response.text.splitlines() if line.startswith('Disallow')]
                console.print(f"[bold green][+] Found valid robots.txt at {url}[/bold green]")
                break
            else:
                console.print(f"[bold yellow][!] Invalid robots.txt at {url} (User-agent not found or other issue)[/bold yellow]")
        except Exception as e:
            console.print(f"[bold red][-] Error retrieving robots.txt from {url}: {e}[/bold red]")

    if not disallows:
        console.print(f"[bold yellow][!] No valid robots.txt found for domain: {domain}[/bold yellow]")

    return disallows

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
@click.pass_context
def domain_insight(ctx):
    """Advanced domain information gathering tool."""
    global current_domain

    while True:
        console.print()
        console.print("[magenta]=============================[/magenta]")
        console.print("[magenta]   Welcome to Domain Insight   [/magenta]")
        console.print("[magenta]=============================[/magenta]")

        if not current_domain:
            set_domain()
        
        console.print(f"[cyan]Current domain: {current_domain}[/cyan]")
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
                console.log(f"[+] DNS records saved to {output_file}")
                display_results([f"{record_type}: {', '.join(records)}" for record_type, records in dns_records.items()])
            elif choice == 4:
                task = progress.add_task("Checking robots.txt...", total=None)
                robots_txt = check_robots_txt(current_domain)
                progress.update(task, completed=True)
                if robots_txt:
                    display_results([f"[+] Disallowed rules in robots.txt:"] + [f" - {rule}" for rule in robots_txt])
                else:
                    console.print("[bold red][-] robots.txt not found on any of the checked URLs.[/bold red]")
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

if __name__ == "__main__":
    domain_insight()

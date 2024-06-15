import requests
import pandas as pd
import xml.etree.ElementTree as ET
import gzip
import click
from tqdm import tqdm
from urllib.parse import urlparse

NAMESPACE = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

def download_sitemap(url):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        if url.endswith('.gz'):
            with gzip.GzipFile(fileobj=response.raw) as f:
                return ET.parse(f).getroot()
        else:
            return ET.fromstring(response.content)
    except requests.RequestException as e:
        click.echo(click.style(f"Error downloading sitemap: {e}", fg="red"))
        return None
    except ET.ParseError as e:
        click.echo(click.style(f"Error parsing sitemap: {e}", fg="red"))
        return None

def parse_sitemap(root, urls, sitemap_name, level=0):
    sitemaps = root.findall('ns:sitemap', NAMESPACE)
    if sitemaps:
        click.echo(click.style(f"Found {len(sitemaps)} nested sitemaps. Parsing...", fg="blue"))
        for i, sitemap in enumerate(tqdm(sitemaps, desc="Parsing sitemaps", colour="cyan"), start=1):
            loc = sitemap.find('ns:loc', NAMESPACE).text
            click.echo(click.style(f"Parsing sitemap {i}/{len(sitemaps)}: {loc}", fg="yellow"))
            sitemap_root = download_sitemap(loc)
            if sitemap_root:
                parse_sitemap(sitemap_root, urls, loc, level + 1)
    else:
        url_count = len(root.findall('ns:url', NAMESPACE))
        click.echo(click.style(f"Parsing {url_count} URLs in sitemap...", fg="blue"))
        for url_elem in tqdm(root.findall('ns:url', NAMESPACE), desc="Parsing URLs", colour="cyan"):
            loc = url_elem.find('ns:loc', NAMESPACE).text
            lastmod = url_elem.find('ns:lastmod', NAMESPACE).text if url_elem.find('ns:lastmod', NAMESPACE) is not None else ''
            changefreq = url_elem.find('ns:changefreq', NAMESPACE).text if url_elem.find('ns:changefreq', NAMESPACE) is not None else ''
            priority = url_elem.find('ns:priority', NAMESPACE).text if url_elem.find('ns:priority', NAMESPACE) is not None else ''
            
            # Check for additional types of sitemaps (image, video, news)
            images = url_elem.findall('ns:image', NAMESPACE)
            image_data = []
            for image in images:
                image_loc = image.find('ns:loc', NAMESPACE).text
                image_caption = image.find('ns:caption', NAMESPACE).text if image.find('ns:caption', NAMESPACE) is not None else ''
                image_data.append({'loc': image_loc, 'caption': image_caption})
            
            videos = url_elem.findall('ns:video', NAMESPACE)
            video_data = []
            for video in videos:
                video_loc = video.find('ns:content_loc', NAMESPACE).text if video.find('ns:content_loc', NAMESPACE) is not None else ''
                video_title = video.find('ns:title', NAMESPACE).text if video.find('ns:title', NAMESPACE) is not None else ''
                video_data.append({'loc': video_loc, 'title': video_title})
            
            news = url_elem.findall('ns:news', NAMESPACE)
            news_data = []
            for news_item in news:
                news_publication_date = news_item.find('ns:publication_date', NAMESPACE).text if news_item.find('ns:publication_date', NAMESPACE) is not None else ''
                news_title = news_item.find('ns:title', NAMESPACE).text if news_item.find('ns:title', NAMESPACE) is not None else ''
                news_data.append({'publication_date': news_publication_date, 'title': news_title})
            
            urls.append({
                'sitemap_name': sitemap_name,
                'loc': loc,
                'lastmod': lastmod,
                'changefreq': changefreq,
                'priority': priority,
                'images': image_data,
                'videos': video_data,
                'news': news_data
            })

@click.command()
def site_mapper():
    """Download and parse sitemaps, export URLs to CSV."""
    sitemap_url = click.prompt(click.style("Enter the URL of the sitemap (supports .xml and .gz)", fg="cyan", bold=True))
    output_file = click.prompt(click.style("Enter the path to the output CSV file", fg="cyan", bold=True), type=click.Path())
    
    urls = []
    click.echo(click.style("Downloading and parsing sitemap...", fg="green", bold=True))
    root = download_sitemap(sitemap_url)
    if root:
        parse_sitemap(root, urls, sitemap_url)
        df = pd.DataFrame(urls)
        df.to_csv(output_file, index=False)
        click.echo(click.style(f"Sitemap data saved to {output_file}", fg="green", bold=True))
    else:
        click.echo(click.style("Failed to process sitemap.", fg="red", bold=True))

if __name__ == "__main__":
    site_mapper()

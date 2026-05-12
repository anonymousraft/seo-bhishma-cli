
# SEO Bhishma

![GitHub release (latest by date)](https://img.shields.io/github/v/release/anonymousraft/seo-bhishma-cli)
![Python Version](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue)
![Forks](https://img.shields.io/github/forks/anonymousraft/seo-bhishma-cli?style=social)
![Build Status](https://github.com/anonymousraft/seo-bhishma-cli/actions/workflows/python-publish.yml/badge.svg)

**SEO Bhishma v3** is an AI-native SEO toolkit. Talk to it like an assistant — it picks the right tool (sitemap parser, indexing checker, Search Console fetcher, backlink verifier, keyword clusterer, cannibalization detector, domain analyzer, redirect mapper, sitemap generator) and runs it for you. The same toolkit is also exposed as:

- a **legacy numbered menu** for users who prefer the v2 workflow,
- **direct subcommands** for scripts/CI, and
- an **MCP server** for external clients like Claude Desktop.

```text
You> is hitendra.io indexed and what tech stack does it use?
[tool] check_indexing_status(url='https://hitendra.io')
✓ Indexed
[tool] tech_stack_analysis(domain='hitendra.io')
Detected: Next.js, Vercel, Tailwind CSS, Google Analytics 4.
```

## Features

- **AI chat** (default) — conversational REPL backed by a LangGraph ReAct agent over 23 SEO tools. Auto-picks OpenAI or Anthropic from env vars; supports `/model`, `/tools`, `/save`, `/menu`, `/clear`.
- **Tiered tool authorization** — read-only tools auto-run; cost/time-sensitive tools (Search Console, OpenAI embeddings, batch ops) confirm once per session; file-writing tools confirm every time.
- **LinkSniper** — bulk backlink verification with anchor-text and `rel`/dofollow checks.
- **SiteMapper** — download and parse sitemaps, including nested + gzipped, with image/video/news extensions.
- **IndexSpy** — bulk indexing checker with proxy rotation and CAPTCHA handling.
- **KeywordSorcerer** — OpenAI-embedding keyword clusterer (KMeans / Agglomerative / DBSCAN / Spectral).
- **Sitemap Generator** — single or nested, compressed sitemap output from a URL list.
- **GSC Probe** — Search Console analytics, sitemaps, and bulk URL inspection.
- **Redirection Genius** — NLP-based redirect URL mapping (TF-IDF over slugs + optional page-content comparison).
- **Hannibal** — URL cannibalization detection from a GSC export.
- **Domain Insights** — DNS / WHOIS / SSL / robots.txt / tech stack / security headers / reverse-IP / subdomain enumeration.

## Installation

### Linux and macOS

1. Open your terminal.
2. Install the package using `pipx`:
   ```sh
   pip install pipx
   pipx ensurepath
   pipx install seo-bhishma
   ```  

### Windows

1. Open PowerShell or terminal.
2. Install Scoop:
   ```sh
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

   Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
   ```
3. Install `pipx` using Scoop:
   ```sh
   scoop install pipx
   ```
4. Install the package using `pipx`:
   ```sh
   pipx install seo-bhishma
   ```


You can also install the package via pip:

```bash
pip install seo-bhishma
```

## Quick start

### 1. Set an API key

The AI chat needs one of these env vars:

```bash
export SEO_BHISHMA_OPENAI_API_KEY=sk-...      # macOS / Linux
# or
setx SEO_BHISHMA_OPENAI_API_KEY sk-...        # Windows

# Or use Anthropic instead:
export SEO_BHISHMA_ANTHROPIC_API_KEY=sk-ant-...
```

See `.env.example` for the full list (Google Search Console OAuth path, CAPTCHA service, spaCy model, etc.). The CLI also reads a local `.env` file in the current directory.

### 2. Launch

```bash
seo-bhishma
```

On first launch a one-time wizard asks whether you want AI chat or the numbered menu as the default. Switch later with `seo-bhishma set-default chat` or `seo-bhishma set-default menu`. You can always force a specific interface:

```bash
seo-bhishma chat     # AI agent REPL (default for new users)
seo-bhishma menu     # legacy numbered menu
```

### 3. Talk to the agent

```text
You> pull last 7 days of GSC clicks for sc-domain:example.com, top 10 pages
[tool] gsc_fetch_search_analytics(site_url='sc-domain:example.com', start_date='2026-05-05', end_date='2026-05-11', dimensions=['page'], row_limit=10)
| page                  | clicks | impressions | ctr   | position |
| /                     | 482    | 9.1k        | 5.3%  | 4.2      |
| /blog/seo-checklist   | 311    | 5.7k        | 5.5%  | 6.1      |
...
✓ Saved 10 rows to gsc_20260512_103412.csv.
```

Slash commands inside chat: `/help`, `/tools`, `/clear`, `/menu`, `/model <name>`, `/save [path]`, `/quit`.

## Direct subcommands

Every tool also runs standalone — useful for scripts, cron jobs, or CI:

```bash
seo-bhishma link-sniper
seo-bhishma site-mapper
seo-bhishma index-spy
seo-bhishma keyword-sorcerer
seo-bhishma gsc-probe
seo-bhishma redirection-genius
seo-bhishma domain-insight
seo-bhishma hannibal
seo-bhishma sitemap-generator
```

## MCP server

Expose all 34 SEO tools to Claude Desktop, MCP-aware IDEs, or any FastMCP client:

```bash
seo-bhishma-mcp
```

Point your MCP client at this command (stdio transport).

## Legacy numbered menu

Run with `seo-bhishma menu`. You will see the following menu:

```           
█▀ █▀▀ █▀█  █▄▄ █░█ █ █▀ █░█ █▀▄▀█ ▄▀█ 
▄█ ██▄ █▄█  █▄█ █▀█ █ ▄█ █▀█ █░▀░█ █▀█ 
           
v2.0, @hi7endra

Giving back to the community.
Support: https://t.ly/hitendra

╭────┬────────────────────╮
│ 1. │ GSC Probe          │
│ 2. │ Domain Insights    │
│ 3. │ Keyword Sorcerer   │
│ 4. │ Hannibal           │
│ 5. │ IndexSpy           │
│ 6. │ Redirection Genius │
│ 7. │ LinkSniper         │
│ 8. │ SiteMapper         │
│ 9. │ Sitemap Generator  │
│ 0. │ Exit               │
╰────┴────────────────────╯
Enter your choice [1/2/3/4/5/6/7/8/9/0]:                                  
```

Select an option by entering the corresponding number.

### LinkSniper

Check if backlinks are live and verify anchor texts.

#### Check a Single URL

```bash
seo-bhishma link-sniper
```

Follow the prompts to enter the backlink URL, target URL, and the expected anchor text.

Example:

```
Enter the backlink URL: https://example.com
Enter the target URL: https://example.com/target
Enter the expected anchor text (optional): Example Anchor
```

#### Check URLs from a File

```bash
seo-bhishma link-sniper
```

Follow the prompts to enter the path to the input file (CSV/JSON) and the output CSV file.

Example:

```
Enter the path to the input file (CSV/JSON): bulk_test.csv
Enter the path to the output CSV file: output.csv
```

### SiteMapper

Download and parse sitemaps, export URLs to CSV.

```bash
seo-bhishma site-mapper
```

Follow the prompts to enter the URL of the sitemap and the path to the output CSV file.

Example:

```
Enter the URL of the sitemap (supports .xml and .gz): https://example.com/sitemap.xml
Enter the path to the output CSV file: sitemap_output.csv
```

### IndexSpy

Bulk indexing checker.

```bash
seo-bhishma index-spy
```

Follow the prompts to enter the required information.

Example:

```
Enter the URL to check indexing status: https://example.com
```

#### Bulk Indexing Checker

Check the indexing status of multiple URLs:

```bash
seo-bhishma index-spy
```
##### Features

1. Proxy Support: Supports HTTP, HTTPS, SOCKS4, and SOCKS5 proxies.
2. CAPTCHA Handling: Automatically switches proxies and user-agents to handle CAPTCHAs.
3. Progress Bar: Displays progress during the bulk checking process.
4. Error Handling: Provides robust error handling and status messages.

##### Usage
Follow the prompts to provide the input file, proxy settings, and other options.

### Keyword Clustering

Cluster keywords based on semantic relevance:

```bash
seo-bhishma keyword-sorcerer
```

#### Features

1. OpenAI GPT-4: Uses OpenAI's GPT-4 to generate embeddings for the keywords.
2. Clustering Algorithms: Supports multiple clustering algorithms:
    - KMeans
    - Agglomerative Clustering
    - DBSCAN
    - Spectral Clustering
3. Optimal Clusters: Automatically determines the optimal number of clusters based on the number of keywords.
4. Intent-Based Clustering: Clusters keywords based on their semantic intent.
5. Error Handling: Provides robust error handling and status messages.

Usage
Follow the prompts to provide the input file, output file, and choose the clustering method.

### Sitemap Generator
Generate sitemaps from a list of URLs:

```bash
seo-bhishma sitemap-generator
```

#### Features
1. Single Sitemap: Generate a single sitemap from a list of URLs.
2. Nested Sitemaps: Supports generating nested sitemaps with a specified URL limit per sitemap.
3. Compressed Sitemaps: Option to create compressed sitemaps.
4. Priority and Frequency: Allows setting priority and change frequency for the URLs.
5. Error Handling: Provides robust error handling and status messages.

#### Usage
Follow the prompts to provide the input file, output file, and other options.


## Contributing

We welcome contributions! Please follow these steps to contribute:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature-name`).
3. Make your changes.
4. Commit your changes (`git commit -m 'Add some feature'`).
5. Push to the branch (`git push origin feature/your-feature-name`).
6. Open a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgements

- [Click](https://click.palletsprojects.com/) for creating the CLI framework.
- [Requests](https://docs.python-requests.org/en/latest/) for making HTTP requests simple.
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for parsing HTML and XML documents.
- [Pandas](https://pandas.pydata.org/) for data manipulation and analysis.
- [TQDM](https://tqdm.github.io/) for progress bars in Python.

## Contact

Author: Hitendra Singh Rathore 
GitHub: [anonymousraft](https://github.com/anonymousraft)
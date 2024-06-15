
# SEO Bhishma CLI

SEO Bhishma CLI is a comprehensive CLI tool designed for various SEO-related tasks, such as checking backlinks, downloading and parsing sitemaps, and bulk indexing checking. It provides a suite of tools to help SEO professionals streamline their workflow and improve website performance.

## Features

- **LinkSniper**: Check if backlinks are live and verify anchor texts.
- **SiteMapper**: Download and parse sitemaps, including nested sitemaps and various sitemap types (image, video, news), and export URLs to CSV.
- **IndexSpy**: Bulk indexing checker.

## Installation

You can install the package via pip:

```bash
pip install seo-bhishma-cli
```

## Usage

After installation, you can use the `seo-bhishma-cli` command to access the tools.

### Main Menu

Run the following command to access the main menu:

```bash
seo-bhishma-cli
```

You will see the following menu:

```
Welcome to SEO Bhishma CLI!
Version: 1.0.0
Author: @hi7endra

1. LinkSniper - Check Backlinks
2. SiteMapper - Download Sitemap
3. IndexSpy - Bulk Indexing Checker
4. Exit
```

Select an option by entering the corresponding number.

### LinkSniper

Check if backlinks are live and verify anchor texts.

#### Check a Single URL

```bash
seo-bhishma-cli link_sniper
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
seo-bhishma-cli link_sniper
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
seo-bhishma-cli site_mapper
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
seo-bhishma-cli index_spy
```

Follow the prompts to enter the required information.

Example:

```
Enter the URL to check indexing status: https://example.com
```

## Project Structure

```
seo_blackbox/
│
├── seo_blackbox/
│   ├── __init__.py
│   ├── cli.py
│   ├── constants.py
│   ├── link_sniper.py
│   ├── site_mapper.py
│   └── index_spy.py
│
├── setup.py
├── README.md
├── requirements.txt
└── MANIFEST.in
```

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
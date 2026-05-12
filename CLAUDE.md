# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SEO Bhishma CLI is a Python CLI toolkit (v2.0.0) for SEO professionals. It bundles 9 independent SEO tools behind a single interactive menu and is distributed via PyPI.

## Build & Run Commands

```bash
# Install in development mode
pip install -e .

# Install dependencies only
pip install -r requirements.txt

# Run the CLI (interactive menu)
seo-bhishma-cli

# Run a specific sub-command directly
seo-bhishma-cli link_sniper
seo-bhishma-cli site_mapper
seo-bhishma-cli index_spy
seo-bhishma-cli keyword_sorcerer
seo-bhishma-cli gsc_probe
seo-bhishma-cli redirection_genius
seo-bhishma-cli domain_insight
seo-bhishma-cli hannibal
seo-bhishma-cli sitemap_generator

# Build distribution package
python -m build
```

There are no tests (`tests/` is excluded in setup.py but the directory does not exist). There is no linter or formatter configured.

## Architecture

### Entry Point & Command Registration

`seo_bhishma_cli/cli.py` is the entry point (`console_scripts` → `seo_bhishma_cli.cli:cli`). It defines a Click `@click.group` that shows an ASCII art intro and an interactive numbered menu. Each tool module exports a single Click `@click.command()` function, registered via `cli.add_command()` at the bottom of `cli.py`.

### Module Pattern

Every tool module follows the same structure:
1. Imports from `seo_bhishma_cli.common` (wildcard import providing Click, Pandas, Requests, Rich, signal, logging, constants, etc.)
2. Defines a single `@click.command()` function (same name as the module)
3. Runs an internal `while True` menu loop with Rich prompts (single item vs batch vs exit)
4. Uses signal handlers (SIGINT/SIGTERM) for graceful shutdown and temp-file progress saving
5. Saves results to CSV via Pandas

### Adding a New Tool

1. Create `seo_bhishma_cli/new_tool.py` with a `@click.command()` named `new_tool`
2. Add `from .new_tool import new_tool` to `seo_bhishma_cli/__init__.py` and include it in `__all__`
3. Import and `cli.add_command(new_tool)` in `cli.py`
4. Add a menu entry in the `menu()` function's table and choice handler

### Shared Utilities

`seo_bhishma_cli/common/__init__.py` is a barrel file that re-exports: `os`, `sys`, `click`, `pandas`, `requests`, `gzip`, `logging`, `json`, `time`, `signal`, `csv`, `urlparse`, `Path`, `subprocess`, Rich components (`Console`, `Prompt`, `Progress`, `Panel`, `RichHandler`), and constants (`CLI_NAME`, `CLI_VERSION`, `CLI_AUTHOR`, `CLI_MESSAGE`). All modules use `from seo_bhishma_cli.common import *`.

### Key External Dependencies

- **CLI framework**: Click (commands, options, groups)
- **Terminal UI**: Rich (tables, panels, progress bars, prompts, logging)
- **Browser automation**: Playwright (index_spy, domain_insight) — requires `playwright install`
- **ML/NLP**: scikit-learn (clustering), spaCy (slug analysis in redirection_genius), sentence-transformers (embeddings in hannibal)
- **AI**: OpenAI API (GPT-4 embeddings in keyword_sorcerer) — requires API key
- **Google**: google-auth + google-api-python-client (GSC OAuth in gsc_probe) — requires credentials JSON

### Version Management

Version is hardcoded in `seo_bhishma_cli/constants.py` (`CLI_VERSION`) and `setup.py` (`version`). Both must be updated together for a release.

### CI/CD

GitHub Actions workflow (`.github/workflows/python-publish.yml`) builds and publishes to PyPI on GitHub release creation. Requires `PYPI_API_TOKEN` secret.

### Generated Files (gitignored)

Config/state: `config.yaml`, `progress.yaml`, `token.pickle`. Output: `gsc_data/`, `sitemaps/`, `*.csv`, `*.xml`, `*_reverse_ip_*.txt`, `*_subdomains_*.txt`, `*_dns_records_*.txt`.

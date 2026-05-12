# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SEO Bhishma is a Python toolkit (v3.0.0) for SEO professionals. It ships **four** usable surfaces from a single source tree:

1. **AI chat (default)** — `seo-bhishma` launches a conversational REPL backed by a LangGraph ReAct agent with 23 SEO tools.
2. **Legacy menu** — `seo-bhishma menu` opens the v2-style numbered menu (still useful for one-shot interactive workflows).
3. **Direct subcommands** — `seo-bhishma link-sniper`, `seo-bhishma gsc-probe`, etc. for scripts/CI.
4. **MCP server** — `seo-bhishma-mcp` exposes 34 tools over the Model Context Protocol for external MCP clients (Claude Desktop, IDEs).

On first launch, the CLI runs a one-time wizard asking which of chat or menu should be the default for bare `seo-bhishma`. Switch later with `seo-bhishma set-default chat|menu`.

## Build & Run Commands

```bash
# Install in development mode (pulls langgraph + langchain + fastmcp; pytest/ruff in [dev])
pip install -e ".[dev]"

# First run — wizard chooses default. Subsequent runs honor the saved preference.
seo-bhishma

# Force a specific interface
seo-bhishma chat               # AI agent REPL
seo-bhishma menu               # legacy numbered menu

# Change the saved default
seo-bhishma set-default chat
seo-bhishma set-default menu

# Run an individual tool directly
seo-bhishma link-sniper
seo-bhishma site-mapper
seo-bhishma index-spy
seo-bhishma keyword-sorcerer
seo-bhishma gsc-probe
seo-bhishma redirection-genius
seo-bhishma domain-insight
seo-bhishma hannibal
seo-bhishma sitemap-generator

# Run the MCP server (stdio transport — point your MCP client at this command)
seo-bhishma-mcp

# Tests
pytest -q

# Lint
ruff check src tests

# Build distribution package
python -m build
```

## AI chat — usage

The chat REPL picks an LLM provider automatically:

1. If `SEO_BHISHMA_LLM_PROVIDER` is set, it wins.
2. Else if `SEO_BHISHMA_OPENAI_API_KEY` is non-empty → OpenAI (default model: `gpt-4o-mini`).
3. Else if `SEO_BHISHMA_ANTHROPIC_API_KEY` is non-empty → Anthropic (default model: `claude-sonnet-4-5`).
4. Else `seo-bhishma chat` exits with a clear "set one of these env vars" error.

### Slash commands in chat

| Command | What it does |
|---|---|
| `/help` | Cheat sheet |
| `/tools` | List all 23 tools with their authorization tier |
| `/clear` | Start a fresh conversation (drops history) |
| `/menu` | Drop into the legacy numbered menu |
| `/model <name>` | Switch model mid-session (e.g. `/model gpt-4o`) |
| `/save [path]` | Save the transcript as Markdown |
| `/quit` / `/exit` | Leave chat |

### Tool authorization tiers

Each tool registered by the agent has an `auth_tier` in its metadata, consumed by the chat REPL to decide whether to interrupt for user confirmation:

- **`auto`** (13 tools) — read-only / fast. Runs without asking. Examples: `check_backlink`, `get_dns_records`, `parse_sitemap`, `gsc_list_sites`, `tech_stack_analysis`.
- **`confirm_once`** (8 tools) — costs money, takes a while, or hits a paid API. Asks once per session per tool name; the answer is remembered for the rest of the chat. Examples: `gsc_fetch_search_analytics`, `cluster_keywords`, `batch_check_indexing`, `find_subdomains`.
- **`confirm_each`** (2 tools) — writes a file. Asks every time. Examples: `generate_sitemap`, `generate_nested_sitemaps`.

The classification lives in `src/seo_bhishma/agents/tools.py`; tier checks live in `agents/graph.py:ToolAuthSession` and `needs_user_confirmation()`.

## Architecture

Clean separation between **logic** (`core/`, `models/`) and **frontends** (`cli/`, `mcp/`, `agents/`). Logic modules have no UI dependencies and accept optional `on_progress` callbacks; frontends own all user interaction.

```
src/seo_bhishma/
├── core/            # Pure business logic — no Click, no Rich. Returns Pydantic models.
├── models/          # Pydantic v2 IO models, one file per tool.
├── cli/             # Click-based CLI surfaces.
│   ├── app.py       # `seo-bhishma` entry point — wizard + dispatch + menu/set-default commands.
│   ├── preferences.py  # Persistent user preference (chat vs menu default).
│   ├── _ui.py       # Shared Rich helpers (console, tool_panel, make_progress).
│   └── commands/    # One file per command. chat.py is the AI REPL; others are the legacy menu tools.
├── agents/          # LangGraph ReAct agent that powers `seo-bhishma chat`.
│   ├── llm.py       # Provider abstraction (OpenAI + Anthropic, auto-detected from settings).
│   ├── tools.py     # 23 LangChain @tool wrappers around core/ functions, with auth tiers.
│   ├── prompts.py   # SEO-specific system prompt for the agent.
│   └── graph.py     # `build_agent()`, `ToolAuthSession`, classify_tool_calls/needs_user_confirmation.
├── mcp/             # FastMCP server for external MCP clients.
│   ├── server.py    # `seo-bhishma-mcp` entry point.
│   ├── tools/       # One file per tool group (backlinks.py, indexing.py, …).
│   └── resources/   # MCP resources (e.g. sitemap.py).
├── config/          # Settings + constants.
│   ├── settings.py  # Reads env vars with `SEO_BHISHMA_` prefix; resolve_provider/resolve_model logic.
│   └── constants.py # CLI_NAME, CLI_VERSION, CLI_AUTHOR, CLI_MESSAGE.
└── skills/          # Empty stub (reserved for future use).
```

### Preferences file

The first-run wizard writes a preferences YAML to:

- `$SEO_BHISHMA_HOME/preferences.yaml` if `SEO_BHISHMA_HOME` is set (used in tests).
- `%APPDATA%\seo-bhishma\preferences.yaml` on Windows.
- `~/.config/seo-bhishma/preferences.yaml` on POSIX.

Only one key today: `default_interface: chat | menu`. The format is forward-compatible.

### Adding a New Tool

1. Add core logic in `src/seo_bhishma/core/<new_tool>.py` — pure functions returning Pydantic models, no Click/Rich imports.
2. Add Pydantic IO models in `src/seo_bhishma/models/<new_tool>.py`.
3. Add tests under `tests/core/test_<new_tool>.py`.
4. Add a CLI command at `src/seo_bhishma/cli/commands/<new_tool>.py` (Click `@click.command()` wrapping the core function, using `console`/`make_progress`/`tool_panel` from `cli/_ui.py`).
5. Register the command in `src/seo_bhishma/cli/commands/__init__.py` (imports + `__all__`) and add a row to `_MENU_ITEMS` in `cli/app.py`.
6. **For the AI chat** — add a `@tool`-decorated wrapper in `src/seo_bhishma/agents/tools.py` and append it to `_AUTO` / `_CONFIRM_ONCE` / `_CONFIRM_EACH` based on its cost/risk profile.
7. Optionally expose it via MCP at `src/seo_bhishma/mcp/tools/<group>.py` and register in `mcp/server.py`.

### Configuration

`seo_bhishma.config.settings.Settings` reads environment variables prefixed `SEO_BHISHMA_` and falls back to a local `.env` file. See `.env.example` for the full set:

- `SEO_BHISHMA_LLM_PROVIDER`, `SEO_BHISHMA_LLM_MODEL` (empty → auto-detect)
- `SEO_BHISHMA_OPENAI_API_KEY`, `SEO_BHISHMA_ANTHROPIC_API_KEY`
- `SEO_BHISHMA_GSC_CREDENTIALS_PATH`, `SEO_BHISHMA_GSC_TOKEN_PATH`
- `SEO_BHISHMA_CAPTCHA_SERVICE`, `SEO_BHISHMA_CAPTCHA_API_KEY`
- `SEO_BHISHMA_SPACY_MODEL`, `SEO_BHISHMA_LOG_LEVEL`

`keyword_sorcerer` also keeps an OpenAI key in a local `config.yaml` for backward compatibility with the v2 prompt flow.

### Key External Dependencies

- **CLI**: Click
- **Terminal UI**: Rich (tables, panels, progress bars, prompts)
- **AI agents**: langgraph, langchain-core, langchain-openai, langchain-anthropic (base deps — chat is the default UX)
- **MCP**: fastmcp (base dep)
- **Browser automation**: Playwright (index_spy, domain_insight) — requires `playwright install chromium`
- **ML/NLP**: scikit-learn (clustering), spaCy (slug analysis in redirection_genius), sentence-transformers (embeddings in hannibal)
- **AI calls outside the agent**: OpenAI API (keyword_sorcerer embeddings)
- **Google**: google-auth + google-api-python-client (GSC OAuth in gsc_probe) — requires OAuth client credentials JSON

### Version Management

Version lives in two places that must move together:
- `pyproject.toml` → `project.version`
- `src/seo_bhishma/config/constants.py` → `CLI_VERSION`

`src/seo_bhishma/__init__.py` also exposes `__version__`.

### CI/CD

GitHub Actions workflow (`.github/workflows/python-publish.yml`) builds and publishes to PyPI on GitHub release creation. Requires `PYPI_API_TOKEN` secret. There is currently no lint/test workflow — `pytest` and `ruff check src tests` should be added to a `ci.yml`.

### Generated Files (gitignored)

Config/state: `config.yaml`, `progress.yaml`, `token.pickle`, `~/.config/seo-bhishma/preferences.yaml`. Output: `gsc_data/`, `sitemaps/`, `*.csv`, `*.xml`, `*_reverse_ip_*.txt`, `*_subdomains_*.txt`, `*_dns_records_*.txt`, `chat_*.md` (chat transcripts).

---
name: markdown-for-agents
description: Fetch web content as clean markdown using Cloudflare's conversion services. Use when fetching URL content where structured markdown is preferred over raw text extraction. Supports content negotiation, Workers AI, and Browser Rendering with automatic fallback.
version: "1.0.0"
author: Amram Englander
license: MIT
tags: ["markdown", "web-fetch", "cloudflare", "ai-agents", "llm-tools"]
metadata:
  openclaw:
    requires:
      env:
        - CLOUDFLARE_ACCOUNT_ID
        - CLOUDFLARE_API_TOKEN
      bins:
        - python3
    primaryEnv: CLOUDFLARE_API_TOKEN
    emoji: "\U0001F4DD"
    homepage: https://github.com/arsolutioner/markdown-for-agents
    os:
      - macos
      - linux
      - windows
---

# Markdown for Agents Skill

## Overview

Fetches web content as clean markdown using a cascading chain of three Cloudflare conversion methods. Produces structured markdown that preserves headings, links, and formatting -- ideal for AI consumption with ~80% fewer tokens than HTML.

## Quick Start

**No setup needed for basic usage:**
```bash
python3 scripts/fetch_markdown.py "https://blog.cloudflare.com/markdown-for-agents/"
```

**For full Cloudflare API access (optional):**
Set environment variables:
```
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_api_token
```

Or add to `~/.claude/.env` (Claude Code) or the equivalent env file for your platform.

## How It Works

The skill tries three methods in order, stopping at the first success:

| # | Method | Credentials | Best For |
|---|--------|-------------|----------|
| 1 | **Content Negotiation** (`Accept: text/markdown`) | None | Cloudflare sites with feature enabled |
| 2 | **Workers AI toMarkdown** REST API | Required | HTML/PDF/Office docs from any site |
| 3 | **Browser Rendering /markdown** REST API | Required | JS-heavy SPAs, dynamic pages |

### Method 1: Content Negotiation

Sends `Accept: text/markdown` header. If the site is behind Cloudflare with "Markdown for Agents" enabled, it returns markdown directly from the CDN edge.

- **Credentials**: None
- **Cost**: Free
- **File types**: HTML only

```bash
python3 scripts/fetch_markdown.py "https://blog.cloudflare.com/markdown-for-agents/" --method negotiate
```

### Method 2: Workers AI toMarkdown

Downloads the file, uploads it to Cloudflare's `toMarkdown` REST API. The most versatile method -- handles PDFs, Office docs, images, and more.

- **Credentials**: `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`
- **Cost**: Free for text docs. Images may consume Neurons.
- **File types**: HTML, PDF, images, Word, Excel, CSV, XML, Open Document, Apple Numbers

```bash
python3 scripts/fetch_markdown.py "https://example.com/report.pdf" --method workers-ai -t 120
```

### Method 3: Browser Rendering

Sends the URL to Cloudflare's headless Chromium, which renders the page fully (including JavaScript), then converts to markdown.

- **Credentials**: `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`
- **Cost**: Free plan: 10 min/day. Paid: 10 hrs/month then $0.09/hr.
- **File types**: HTML only. Does NOT work on PDFs.

```bash
python3 scripts/fetch_markdown.py "https://spa-app.com" --method browser-rendering
```

## Usage

### Basic
```bash
python3 scripts/fetch_markdown.py "https://example.com"
python3 scripts/fetch_markdown.py "https://example.com" -f json
python3 scripts/fetch_markdown.py "https://example.com" --include-metadata
```

### Force a Specific Method
```bash
python3 scripts/fetch_markdown.py "https://example.com" --method negotiate
python3 scripts/fetch_markdown.py "https://example.com" --method workers-ai
python3 scripts/fetch_markdown.py "https://spa-app.com" --method browser-rendering
```

### Quiet Mode (for scripts)
```bash
python3 scripts/fetch_markdown.py "https://example.com" -q -f json | jq '.content'
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `url` | Target URL (required) | -- |
| `-f, --format` | Output format: `text`, `json` | `text` |
| `-t, --timeout` | Request timeout in seconds | `30` |
| `--verify-ssl` | Verify SSL certificates | `False` |
| `--method` | Force method: `auto`, `negotiate`, `workers-ai`, `browser-rendering` | `auto` |
| `--no-fallback` | Stop after first method attempt | `False` |
| `--include-metadata` | Prepend metadata to text output | `False` |
| `-q, --quiet` | Suppress stderr status messages | `False` |

## Dependencies

**Required:** Python 3.6+ (standard library only, zero third-party dependencies)

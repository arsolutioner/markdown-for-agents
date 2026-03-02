#!/usr/bin/env python3
"""
Markdown for Agents - Fetch web content as clean markdown using Cloudflare's
conversion services with cascading fallback.

Methods (tried in order):
1. Content negotiation (Accept: text/markdown) - free, no credentials
2. Workers AI toMarkdown REST API - needs CLOUDFLARE credentials
3. Browser Rendering /markdown API - needs CLOUDFLARE credentials
"""

import sys
import urllib.request
import urllib.error
import urllib.parse
import json
import time
import ssl
import re
import argparse
import gzip
import io
import os
from datetime import datetime


def validate_url(url):
    """Validate and normalize URL."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: missing host in {url}")
    return url


def _read_env_file(path, account_id, api_token):
    """Read Cloudflare credentials from a .env file."""
    if not os.path.exists(path):
        return account_id, api_token
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key == 'CLOUDFLARE_ACCOUNT_ID' and not account_id:
                    account_id = value
                elif key == 'CLOUDFLARE_API_TOKEN' and not api_token:
                    api_token = value
    return account_id, api_token


def load_cloudflare_credentials():
    """Load Cloudflare credentials from environment or .env files.

    Checks in order (first found wins):
      1. Environment variables
      2. .env in the script's own directory
      3. .env in the current working directory
      4. ~/.claude/.env (Claude Code)
    """
    account_id = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    api_token = os.environ.get('CLOUDFLARE_API_TOKEN')

    if account_id and api_token:
        return account_id, api_token

    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_paths = [
        os.path.join(script_dir, '.env'),
        os.path.join(os.getcwd(), '.env'),
        os.path.expanduser('~/.claude/.env'),
    ]

    for env_file in env_paths:
        account_id, api_token = _read_env_file(env_file, account_id, api_token)
        if account_id and api_token:
            break

    return account_id, api_token


def _make_ssl_context(verify_ssl):
    """Create SSL context."""
    ctx = ssl.create_default_context()
    if not verify_ssl:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _decompress(data, encoding):
    """Decompress response data if needed."""
    if encoding == 'gzip':
        try:
            return gzip.decompress(data)
        except Exception:
            return data
    elif encoding == 'deflate':
        try:
            import zlib
            return zlib.decompress(data)
        except Exception:
            return data
    return data


def parse_frontmatter(markdown):
    """Extract YAML frontmatter from markdown content.

    Returns (frontmatter_dict, content_without_frontmatter).
    If no frontmatter found, returns ({}, original_content).
    """
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', markdown, re.DOTALL)
    if not match:
        return {}, markdown

    raw = match.group(1)
    frontmatter = {}
    for line in raw.split('\n'):
        if ':' in line:
            key, _, value = line.partition(':')
            frontmatter[key.strip()] = value.strip()

    content = markdown[match.end():]
    return frontmatter, content


def try_content_negotiation(url, timeout=30, verify_ssl=False, quiet=False):
    """Method 1: Request markdown via Accept header content negotiation.

    Returns (content, metadata_dict) or None if markdown not available.
    """
    if not quiet:
        print("  Trying content negotiation (Accept: text/markdown)...", file=sys.stderr)

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; ClaudeCode/1.0; +https://claude.ai)',
        'Accept': 'text/markdown, text/html;q=0.9, */*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
    }

    req = urllib.request.Request(url, headers=headers)
    ctx = _make_ssl_context(verify_ssl)

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            content_type = resp.headers.get('Content-Type', '')

            if 'text/markdown' not in content_type:
                return None

            raw = resp.read()
            encoding = resp.headers.get('Content-Encoding', '')
            data = _decompress(raw, encoding)
            content = data.decode('utf-8', errors='replace')

            metadata = {
                'method': 'content_negotiation',
                'content_type': content_type,
                'markdown_tokens': resp.headers.get('X-Markdown-Tokens'),
                'content_signal': resp.headers.get('Content-Signal'),
            }

            if not quiet:
                tokens = metadata.get('markdown_tokens', 'unknown')
                print(f"  Markdown received ({tokens} tokens)", file=sys.stderr)

            return content, metadata

    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        if not quiet:
            print(f"  Content negotiation failed: {e}", file=sys.stderr)
        return None


def _detect_mime_type(content_type, url):
    """Detect mime type and filename from response content-type and URL."""
    mime_map = {
        'application/pdf': ('.pdf', 'application/pdf'),
        'image/jpeg': ('.jpg', 'image/jpeg'),
        'image/png': ('.png', 'image/png'),
        'image/webp': ('.webp', 'image/webp'),
        'image/svg+xml': ('.svg', 'image/svg+xml'),
        'application/xml': ('.xml', 'application/xml'),
        'text/xml': ('.xml', 'application/xml'),
        'text/csv': ('.csv', 'text/csv'),
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ('.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ('.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        'application/vnd.ms-excel': ('.xls', 'application/vnd.ms-excel'),
    }

    parsed_url = urllib.parse.urlparse(url)
    basename = os.path.basename(parsed_url.path)

    # Try content-type header first
    ct_lower = content_type.split(';')[0].strip().lower() if content_type else ''
    if ct_lower in mime_map:
        ext, mime = mime_map[ct_lower]
        filename = basename if basename and '.' in basename else f'document{ext}'
        return filename, mime

    # Try URL extension
    if basename and '.' in basename:
        ext = '.' + basename.rsplit('.', 1)[-1].lower()
        for mime_ct, (m_ext, m_mime) in mime_map.items():
            if ext == m_ext:
                return basename, m_mime

    # Default to HTML
    filename = basename if basename and '.' in basename else 'page.html'
    if not any(filename.endswith(e) for e in ['.html', '.htm', '.pdf', '.xml', '.csv',
               '.docx', '.xlsx', '.xls', '.jpg', '.jpeg', '.png', '.webp', '.svg']):
        filename = filename + '.html'
    return filename, 'text/html'


def try_workers_ai(url, account_id, api_token, timeout=30, verify_ssl=False, quiet=False):
    """Method 2: Fetch content then convert via Workers AI toMarkdown REST API.

    Supports HTML, PDF, images, Office docs, CSV, XML, and more.
    Returns (content, metadata_dict) or None if conversion fails.
    """
    if not account_id or not api_token:
        if not quiet:
            print("  Skipping Workers AI (no credentials configured)", file=sys.stderr)
        return None

    if not quiet:
        print("  Trying Workers AI toMarkdown...", file=sys.stderr)

    # First, fetch the content from the URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; ClaudeCode/1.0; +https://claude.ai)',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = _make_ssl_context(verify_ssl)

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            content_type = resp.headers.get('Content-Type', '')
            raw = resp.read()
            encoding = resp.headers.get('Content-Encoding', '')
            file_data = _decompress(raw, encoding)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        if not quiet:
            print(f"  Workers AI: failed to fetch content: {e}", file=sys.stderr)
        return None

    # Detect file type and build appropriate multipart request
    filename, mime_type = _detect_mime_type(content_type, url)

    if not quiet:
        size_mb = len(file_data) / (1024 * 1024)
        print(f"  Uploading {filename} ({size_mb:.1f} MB, {mime_type}) to Workers AI...", file=sys.stderr)

    boundary = f'----FormBoundary{int(time.time() * 1000)}'

    body_parts = []
    body_parts.append(f'--{boundary}'.encode())
    body_parts.append(f'Content-Disposition: form-data; name="files"; filename="{filename}"'.encode())
    body_parts.append(f'Content-Type: {mime_type}'.encode())
    body_parts.append(b'')
    body_parts.append(file_data)
    body_parts.append(f'--{boundary}--'.encode())

    body = b'\r\n'.join(body_parts)

    api_url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/tomarkdown'
    api_headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    }
    api_req = urllib.request.Request(api_url, data=body, headers=api_headers, method='POST')

    try:
        # Use longer timeout for API call (large files need more time)
        api_timeout = max(timeout, 120)
        with urllib.request.urlopen(api_req, timeout=api_timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        # Response is an array of conversion results
        if isinstance(result, list) and len(result) > 0:
            item = result[0]
        elif isinstance(result, dict) and 'result' in result:
            # Wrapped response format
            res = result['result']
            item = res[0] if isinstance(res, list) and len(res) > 0 else res
        else:
            if not quiet:
                print(f"  Workers AI: unexpected response format", file=sys.stderr)
            return None

        if item.get('format') == 'error':
            if not quiet:
                print(f"  Workers AI conversion error: {item.get('error', 'unknown')}", file=sys.stderr)
            return None

        content = item.get('data', '')
        if not content:
            if not quiet:
                print("  Workers AI: empty conversion result", file=sys.stderr)
            return None

        metadata = {
            'method': 'workers_ai',
            'markdown_tokens': str(item.get('tokens', '')) or None,
            'mimetype': item.get('mimeType'),
        }

        if not quiet:
            tokens = metadata.get('markdown_tokens', 'unknown')
            print(f"  Workers AI conversion successful ({tokens} tokens)", file=sys.stderr)

        return content, metadata

    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
        if not quiet:
            print(f"  Workers AI API failed: {e}", file=sys.stderr)
        return None


def try_browser_rendering(url, account_id, api_token, timeout=30, quiet=False):
    """Method 3: Convert via Browser Rendering /markdown REST API.

    Returns (content, metadata_dict) or None if conversion fails.
    """
    if not account_id or not api_token:
        if not quiet:
            print("  Skipping Browser Rendering (no credentials configured)", file=sys.stderr)
        return None

    if not quiet:
        print("  Trying Browser Rendering /markdown...", file=sys.stderr)

    api_url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/markdown'
    payload = json.dumps({'url': url}).encode('utf-8')

    api_headers = {
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
    }
    api_req = urllib.request.Request(api_url, data=payload, headers=api_headers, method='POST')

    try:
        with urllib.request.urlopen(api_req, timeout=max(timeout, 60)) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        if not result.get('success'):
            errors = result.get('errors', [])
            msg = errors[0].get('message', 'unknown') if errors else 'unknown'
            if not quiet:
                print(f"  Browser Rendering error: {msg}", file=sys.stderr)
            return None

        content = result.get('result', '')
        if not content:
            if not quiet:
                print("  Browser Rendering: empty result", file=sys.stderr)
            return None

        browser_ms = resp.headers.get('X-Browser-Ms-Used')
        metadata = {
            'method': 'browser_rendering',
            'browser_ms_used': browser_ms,
        }

        if not quiet:
            ms_info = f", {browser_ms}ms browser time" if browser_ms else ""
            print(f"  Browser Rendering successful{ms_info}", file=sys.stderr)

        return content, metadata

    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
        if not quiet:
            print(f"  Browser Rendering API failed: {e}", file=sys.stderr)
        return None


def fetch_markdown(url, method='auto', timeout=30, verify_ssl=False, no_fallback=False, quiet=False):
    """Fetch markdown from URL using cascading methods.

    Returns (content, metadata_dict) or (None, error_metadata).
    """
    url = validate_url(url)
    account_id, api_token = load_cloudflare_credentials()

    methods_tried = []
    result = None

    # Define method order
    if method == 'auto':
        chain = ['negotiate', 'workers-ai', 'browser-rendering']
    else:
        chain = [method]

    for m in chain:
        methods_tried.append(m)

        if m == 'negotiate':
            result = try_content_negotiation(url, timeout, verify_ssl, quiet)
        elif m == 'workers-ai':
            result = try_workers_ai(url, account_id, api_token, timeout, verify_ssl, quiet)
        elif m == 'browser-rendering':
            result = try_browser_rendering(url, account_id, api_token, timeout, quiet)

        if result is not None:
            content, metadata = result
            metadata['methods_tried'] = methods_tried
            metadata['url'] = url
            return content, metadata

        if no_fallback:
            break

    return None, {'methods_tried': methods_tried, 'url': url, 'error': 'All methods failed'}


def format_output(content, metadata, output_format='text', include_metadata=False):
    """Format the result for output."""
    if content is None:
        if output_format == 'json':
            return json.dumps({
                'success': False,
                'url': metadata.get('url', ''),
                'error': metadata.get('error', 'Failed to fetch markdown'),
                'methods_tried': metadata.get('methods_tried', []),
                'timestamp': datetime.now().isoformat(),
            }, indent=2)
        else:
            return None

    if output_format == 'json':
        frontmatter, clean_content = parse_frontmatter(content)
        return json.dumps({
            'success': True,
            'url': metadata.get('url', ''),
            'content': content,
            'method_used': metadata.get('method', 'unknown'),
            'methods_tried': metadata.get('methods_tried', []),
            'markdown_tokens': metadata.get('markdown_tokens'),
            'content_signal': metadata.get('content_signal'),
            'frontmatter': frontmatter if frontmatter else None,
            'length': len(content),
            'lines': content.count('\n'),
            'timestamp': datetime.now().isoformat(),
        }, indent=2)
    else:
        if include_metadata:
            parts = [f"# URL: {metadata.get('url', '')}"]
            parts.append(f"# Method: {metadata.get('method', 'unknown')}")
            if metadata.get('markdown_tokens'):
                parts.append(f"# Tokens: {metadata['markdown_tokens']}")
            if metadata.get('content_signal'):
                parts.append(f"# Content-Signal: {metadata['content_signal']}")
            parts.append('')
            return '\n'.join(parts) + content
        else:
            return content


def main():
    parser = argparse.ArgumentParser(
        description='Fetch web content as markdown using Cloudflare conversion services',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Methods (tried in order when --method=auto):
  1. negotiate        Content negotiation via Accept: text/markdown header
  2. workers-ai       Cloudflare Workers AI toMarkdown REST API
  3. browser-rendering Cloudflare Browser Rendering /markdown REST API

Examples:
  %(prog)s "https://blog.cloudflare.com/markdown-for-agents/"
  %(prog)s "https://example.com" -f json
  %(prog)s "https://example.com" --method workers-ai
  %(prog)s "https://spa-heavy-site.com" --method browser-rendering
        """
    )

    parser.add_argument('url', help='URL to fetch markdown from')
    parser.add_argument('-f', '--format', choices=['text', 'json'],
                        default='text', help='Output format (default: text)')
    parser.add_argument('-t', '--timeout', type=int, default=30,
                        help='Request timeout in seconds (default: 30)')
    parser.add_argument('--verify-ssl', action='store_true',
                        help='Verify SSL certificates (default: disabled)')
    parser.add_argument('--method', choices=['auto', 'negotiate', 'workers-ai', 'browser-rendering'],
                        default='auto', help='Conversion method (default: auto)')
    parser.add_argument('--no-fallback', action='store_true',
                        help='Only try first applicable method, do not cascade')
    parser.add_argument('--include-metadata', action='store_true',
                        help='Include metadata comments in text output')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress status messages on stderr')

    args = parser.parse_args()

    if not args.quiet:
        print(f"Fetching markdown from: {args.url}", file=sys.stderr)

    start = time.time()

    content, metadata = fetch_markdown(
        url=args.url,
        method=args.method,
        timeout=args.timeout,
        verify_ssl=args.verify_ssl,
        no_fallback=args.no_fallback,
        quiet=args.quiet,
    )

    elapsed = time.time() - start

    output = format_output(content, metadata, args.format, args.include_metadata)

    if output:
        print(output)
        if not args.quiet:
            method = metadata.get('method', 'none')
            length = len(content) if content else 0
            lines = content.count('\n') if content else 0
            print(f"Done in {elapsed:.2f}s via {method} ({length} chars, {lines} lines)", file=sys.stderr)
    else:
        if not args.quiet:
            methods = ', '.join(metadata.get('methods_tried', []))
            print(f"Failed to fetch markdown (tried: {methods})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/bin/bash

# Environment loader for Cloudflare API credentials
# Sources CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN from ~/.claude/.env

load_cloudflare_env() {
    # Load environment variables from centralized .claude/.env file
    if [ -f "$HOME/.claude/.env" ]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            # Skip comments and empty lines
            if [[ "$line" =~ ^#.*$ ]] || [[ -z "$line" ]]; then
                continue
            fi
            # Export CLOUDFLARE variables
            if [[ "$line" =~ ^CLOUDFLARE_ ]]; then
                eval "export $line" 2>/dev/null || true
            fi
        done < "$HOME/.claude/.env"
    fi

    # Report status (non-fatal -- credentials are optional)
    if [ -z "$CLOUDFLARE_ACCOUNT_ID" ] || [ -z "$CLOUDFLARE_API_TOKEN" ]; then
        echo "Note: Cloudflare credentials not found in ~/.claude/.env" >&2
        echo "Methods 2 (Workers AI) and 3 (Browser Rendering) will be skipped." >&2
        echo "To enable, add to ~/.claude/.env:" >&2
        echo "  CLOUDFLARE_ACCOUNT_ID=your_account_id" >&2
        echo "  CLOUDFLARE_API_TOKEN=your_api_token" >&2
    fi
}

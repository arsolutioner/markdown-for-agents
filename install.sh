#!/bin/bash
set -e

SKILL_NAME="markdown-for-agents"
REPO_URL="https://github.com/arsolutioner/markdown-for-agents.git"
INSTALL_DIR="${HOME}/.claude/skills/${SKILL_NAME}"

echo "Installing ${SKILL_NAME}..."

# Check if already installed
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation at ${INSTALL_DIR}"
    rm -rf "$INSTALL_DIR"
fi

# Create parent directory
mkdir -p "$(dirname "$INSTALL_DIR")"

# Clone to temp directory and copy skill files
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

git clone --depth 1 --quiet "$REPO_URL" "$TMPDIR/repo"

# Create skill directory with SKILL.md and scripts
mkdir -p "${INSTALL_DIR}/scripts"
cp "$TMPDIR/repo/skills/${SKILL_NAME}/SKILL.md" "${INSTALL_DIR}/SKILL.md"
cp "$TMPDIR/repo/scripts/fetch_markdown.py" "${INSTALL_DIR}/scripts/fetch_markdown.py"
cp "$TMPDIR/repo/scripts/load_env.sh" "${INSTALL_DIR}/scripts/load_env.sh"
chmod +x "${INSTALL_DIR}/scripts/fetch_markdown.py"
chmod +x "${INSTALL_DIR}/scripts/load_env.sh"

echo ""
echo "Installed to: ${INSTALL_DIR}"
echo ""
echo "The skill is now available in Claude Code."
echo ""
echo "Optional: For Cloudflare API access (Workers AI, Browser Rendering),"
echo "add these to your environment or ~/.claude/.env:"
echo ""
echo "  CLOUDFLARE_ACCOUNT_ID=your_account_id"
echo "  CLOUDFLARE_API_TOKEN=your_api_token"
echo ""
echo "Done."

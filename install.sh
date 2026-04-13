#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/Tarek-new/euclid"
PYPI="euclid-tutor"
MIN_PYTHON="3.10"
INSTALL_DIR="$HOME/.euclid"

# ── colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

info()    { echo -e "${CYAN}${BOLD}→${RESET} $*"; }
success() { echo -e "${GREEN}${BOLD}✓${RESET} $*"; }
die()     { echo -e "${RED}${BOLD}✗${RESET} $*" >&2; exit 1; }

# ── banner ─────────────────────────────────────────────────────────────────────
echo -e ""
echo -e "${BOLD}  euclid${RESET}  ${DIM}— the open source AI math tutor${RESET}"
echo -e "  ${DIM}${REPO}${RESET}"
echo -e ""

# ── python check ───────────────────────────────────────────────────────────────
info "Checking Python..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

[ -z "$PYTHON" ] && die "Python ${MIN_PYTHON}+ is required. Install from https://python.org"
success "Python $($PYTHON --version)"

# ── pip check ──────────────────────────────────────────────────────────────────
info "Checking pip..."
$PYTHON -m pip --version &>/dev/null || die "pip not found. Run: $PYTHON -m ensurepip"
success "pip found"

# ── install ────────────────────────────────────────────────────────────────────
info "Installing euclid..."

if $PYTHON -m pip install --quiet --upgrade "$PYPI" 2>/dev/null; then
    success "Installed from PyPI"
else
    info "PyPI not available. Installing from source..."
    command -v git &>/dev/null || die "git is required for source install"
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    git clone --quiet --depth 1 "$REPO" "$TMP/euclid"
    $PYTHON -m pip install --quiet "$TMP/euclid"
    success "Installed from source"
fi

# ── shell config ───────────────────────────────────────────────────────────────
info "Configuring shell..."

SHELL_RC=""
case "$SHELL" in
    */zsh)  SHELL_RC="$HOME/.zshrc"  ;;
    */bash) SHELL_RC="$HOME/.bashrc" ;;
    */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
esac

USER_BIN="$($PYTHON -m site --user-base)/bin"

if [ -n "$SHELL_RC" ] && ! grep -q "euclid" "$SHELL_RC" 2>/dev/null; then
    {
        echo ""
        echo "# euclid"
        echo "export PATH=\"${USER_BIN}:\$PATH\""
        if [ -f "$INSTALL_DIR/.env" ]; then
            echo "export \$(grep -v '^#' $INSTALL_DIR/.env | xargs)"
        fi
    } >> "$SHELL_RC"
    success "Shell configured: $SHELL_RC"
fi

mkdir -p "$INSTALL_DIR"

# ── verify ─────────────────────────────────────────────────────────────────────
info "Verifying install..."
export PATH="$USER_BIN:$PATH"

if command -v euclid &>/dev/null; then
    success "euclid $(euclid version 2>/dev/null || echo 'installed')"
else
    echo -e "\n${DIM}euclid installed but not yet on PATH."
    echo -e "Run: export PATH=\"${USER_BIN}:\$PATH\"${RESET}"
fi

# ── api key setup ──────────────────────────────────────────────────────────────
echo -e ""
echo -e "${BOLD}  Setup${RESET}"
echo -e ""

if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
    echo -e "  Set your API key to get started:"
    echo -e ""
    echo -e "  ${DIM}Anthropic (recommended)${RESET}"
    echo -e "  ${CYAN}export ANTHROPIC_API_KEY=sk-ant-...${RESET}"
    echo -e ""
    echo -e "  ${DIM}OpenAI${RESET}"
    echo -e "  ${CYAN}export OPENAI_API_KEY=sk-...${RESET}"
    echo -e ""
    echo -e "  ${DIM}Ollama — fully offline, no key needed${RESET}"
    echo -e "  ${CYAN}ollama serve${RESET}"
    echo -e ""
    echo -e "  Or run: ${BOLD}euclid setup${RESET}"
else
    success "API key detected"
fi

# ── done ───────────────────────────────────────────────────────────────────────
echo -e ""
echo -e "${GREEN}${BOLD}  euclid is ready.${RESET}"
echo -e ""
echo -e "  ${DIM}Start here:${RESET}"
echo -e "  ${BOLD}euclid assess${RESET}        ${DIM}find your level${RESET}"
echo -e "  ${BOLD}euclid practice${RESET}      ${DIM}start learning${RESET}"
echo -e "  ${BOLD}euclid progress${RESET}      ${DIM}see your knowledge map${RESET}"
echo -e ""

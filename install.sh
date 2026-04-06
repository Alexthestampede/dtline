#!/usr/bin/env bash
set -e

DTLINE_HOME="${DTLINE_HOME:-$HOME/.local/dtline}"
DTLINE_VENV="$DTLINE_HOME/venv"
DTLINE_BIN="$DTLINE_VENV/bin"
ROOT_CA_URL="https://raw.githubusercontent.com/drawthingsai/draw-things-community/main/Libraries/BinaryResources/Resources/root_ca.crt"

echo "=== dtline Installer ==="
echo "Installing to: $DTLINE_HOME"

if [ ! -d "$DTLINE_HOME" ]; then
    mkdir -p "$DTLINE_HOME"
    echo "Created directory: $DTLINE_HOME"
fi

echo ""
echo "Downloading Draw Things root CA certificate..."
curl -sL "$ROOT_CA_URL" -o "$DTLINE_HOME/root_ca.crt"
if [ -f "$DTLINE_HOME/root_ca.crt" ]; then
    echo "✓ Certificate saved to: $DTLINE_HOME/root_ca.crt"
else
    echo "✗ Failed to download certificate"
    exit 1
fi

if [ ! -d "$DTLINE_VENV" ]; then
    echo ""
    echo "Creating virtual environment..."
    PYTHON_CMD=""
    for py in python3.11 python3.12 python3.13 python3; do
        if command -v "$py" >/dev/null 2>&1; then
            PYTHON_CMD="$py"
            break
        fi
    done
    if [ -z "$PYTHON_CMD" ]; then
        echo "✗ Python 3 not found"
        exit 1
    fi
    echo "Using Python: $PYTHON_CMD ($($PYTHON_CMD --version))"
    $PYTHON_CMD -m venv "$DTLINE_VENV"
    echo "✓ Virtual environment created"
else
    echo ""
    echo "Using existing virtual environment: $DTLINE_VENV"
fi

echo ""
echo "Installing dtline package..."
source "$DTLINE_BIN/activate"
pip install --quiet -U pip wheel setuptools
pip install --quiet -e .
pip install "flatbuffers>=24.3.0" 2>/dev/null || true
echo "✓ Package installed"

echo ""
echo "Installing shell completions..."
DTLINE_COMPLETIONS="$DTLINE_HOME/completions"
mkdir -p "$DTLINE_COMPLETIONS"

cat > "$DTLINE_COMPLETIONS/dtline.bash" << 'BASH_EOF'
# dtline bash completion
_dtline_completions() {
    local word="${COMP_WORDS[COMP_CWORD]}"
    local prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    case "$prev" in
        generate|list-models|info|list-presets|list-aspect-ratios|list-negative-prompts|config)
            return 0
            ;;
    esac
    
    if [[ "$word" == -* ]]; then
        COMPREPLY=($(compgen -W "--json --verbose --quiet --dry-run --help" -- "$word"))
    else
        COMPREPLY=($(compgen -W "generate list-models info list-presets list-aspect-ratios list-negative-prompts config" -- "$word"))
    fi
}
complete -F _dtline_completions dtline
BASH_EOF

cat > "$DTLINE_COMPLETIONS/dtline.zsh" << 'ZSH_EOF'
#compdef dtline
_dtline() {
    local -a commands
    commands=(
        'generate:Generate an image'
        'list-models:List available models'
        'info:Get model information'
        'list-presets:List available presets'
        'list-aspect-ratios:List available aspect ratios'
        'list-negative-prompts:List negative prompt presets'
        'config:Show configuration'
    )
    _describe 'command' commands
}
compdef _dtline dtline
ZSH_EOF

echo "✓ Completions installed to: $DTLINE_COMPLETIONS"
echo ""
echo "  To enable bash completions, add to ~/.bashrc:"
echo "    source $DTLINE_COMPLETIONS/dtline.bash"
echo ""
echo "  To enable zsh completions, add to ~/.zshrc:"
echo "    source $DTLINE_COMPLETIONS/dtline.zsh"
echo ""

echo "=== Installation Complete ==="
echo ""
echo "Activate the virtual environment with:"
echo "  source $DTLINE_BIN/activate"
echo ""
echo "Or use dtline directly with:"
echo "  $DTLINE_BIN/dtline"
echo ""
echo "Add to PATH (add to ~/.bashrc or ~/.zshrc):"
echo "  export PATH=\"$DTLINE_BIN:\$PATH\""
echo ""
echo "To update: cd $DTLINE_HOME && git pull && source bin/activate && pip install -e ."

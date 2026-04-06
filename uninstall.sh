#!/usr/bin/env bash
set -e

DTLINE_HOME="${DTLINE_HOME:-$HOME/.local/dtline}"

echo "=== dtline Uninstaller ==="
echo "Removing: $DTLINE_HOME"

if [ -d "$DTLINE_HOME" ]; then
    rm -rf "$DTLINE_HOME"
    echo "✓ Removed $DTLINE_HOME"
else
    echo "dtline not found at $DTLINE_HOME"
fi

echo ""
echo "=== Shell Configuration ==="
echo ""
echo "To complete uninstallation, remove these lines from your shell config:"
echo ""
echo "  # ~/.bashrc or ~/.zshrc"
echo "  source $DTLINE_HOME/completions/dtline.bash  # (or dtline.zsh)"
echo "  export PATH=\"\$HOME/.local/dtline/bin:\$PATH\""
echo ""
echo "Search for 'dtline' in your shell config:"
echo "  grep -l 'dtline' ~/.bashrc ~/.zshrc 2>/dev/null || true"
echo ""
echo "Then edit the file(s) and remove the dtline-related lines."
echo ""
echo "=== Uninstallation Complete ==="

#!/usr/bin/env bash
# Stage canon/ + retrospectives/ → docs/ for GitHub Pages rendering.
# Idempotent. Run after every chapter DAG completes (or CI step).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS="$ROOT/docs"

mkdir -p "$DOCS/chapters" "$DOCS/retrospectives"

# Copy canon chapters
if [[ -d "$ROOT/canon" ]]; then
  find "$ROOT/canon" -maxdepth 1 -name 'chapter_*.md' -print0 \
    | xargs -0 -I{} cp {} "$DOCS/chapters/"
fi

# Copy retrospectives
if [[ -d "$ROOT/retrospectives" ]]; then
  find "$ROOT/retrospectives" -maxdepth 1 -name 'chapter_*.md' -print0 \
    | xargs -0 -I{} cp {} "$DOCS/retrospectives/"
fi

echo "staged:"
echo "  chapters:       $(ls "$DOCS/chapters" 2>/dev/null | wc -l) files"
echo "  retrospectives: $(ls "$DOCS/retrospectives" 2>/dev/null | wc -l) files"

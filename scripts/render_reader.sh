#!/usr/bin/env bash
# Stage canon/ + retrospectives/ → docs/ for GitHub Pages rendering.
# Idempotent. Run after every chapter DAG completes (or CI step).
#
# Also injects prev/next chapter navigation at the end of each chapter file
# based on the sequence of canon chapters present (skips gaps — e.g. if
# ch15 → ch17 are present and ch16 is missing, ch15 next link points to
# ch17 directly).
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

# --- Inject prev/next chapter navigation -----------------------------------
# Build sorted list of chapter numbers actually present in docs/chapters,
# then compute neighbors per file. Skips gaps (ch15 → ch17 if ch16 absent).
python3 - "$DOCS/chapters" <<'PYEOF'
import os, re, sys
from pathlib import Path

chapters_dir = Path(sys.argv[1])
files = sorted(chapters_dir.glob("chapter_*.md"))
if not files:
    print("no chapters to navigate")
    sys.exit(0)

# Extract chapter num from filename like chapter_05.md → 5.
def num_of(path: Path) -> int:
    m = re.match(r"chapter_(\d+)\.md", path.name)
    if not m:
        raise ValueError(f"cannot parse chapter num from {path.name}")
    return int(m.group(1))

ordered = sorted(files, key=num_of)
nums = [num_of(p) for p in ordered]

NAV_DELIM = "<!-- chapter-nav-injected -->"

def build_nav(idx: int) -> str:
    parts = []
    if idx > 0:
        prev_n = nums[idx - 1]
        parts.append(f"[← Chapter {prev_n}](chapter_{prev_n:02d}.md)")
    parts.append("[Index](../index.md)")
    if idx < len(nums) - 1:
        next_n = nums[idx + 1]
        parts.append(f"[Chapter {next_n} →](chapter_{next_n:02d}.md)")
    return NAV_DELIM + "\n\n---\n\n" + " · ".join(parts) + "\n"

for i, path in enumerate(ordered):
    text = path.read_text(encoding="utf-8")
    # Strip prior injected nav (idempotent re-runs).
    if NAV_DELIM in text:
        text = text.split(NAV_DELIM, 1)[0].rstrip() + "\n"
    nav = build_nav(i)
    path.write_text(text.rstrip() + "\n\n" + nav, encoding="utf-8")
print(f"chapter nav injected on {len(ordered)} files")
PYEOF

echo "staged:"
echo "  chapters:       $(ls "$DOCS/chapters" 2>/dev/null | wc -l) files"
echo "  retrospectives: $(ls "$DOCS/retrospectives" 2>/dev/null | wc -l) files"

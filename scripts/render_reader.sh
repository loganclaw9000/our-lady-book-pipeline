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

CHAPTER_HERO_IMAGE = {
    1:  ("cover-la-nina.webp",          "La Niña de Córdoba on the Veracruz quay at dusk"),
    8:  ("cholula-courtyard.webp",      "Cholula courtyard, dawn — Reliquaries in their cradles"),
    10: ("huitzilopochtli-engine.webp", "A Huitzilopochtli engine at the Templo Mayor"),
    14: ("great-engine-sleeping.webp",  "The dormant Quetzalcoatl Great Engine, Templo Mayor"),
    17: ("noche-triste.webp",           "La Noche Triste — the Tlacopan causeway, midnight rain"),
    19: ("brigantine-workshop.webp",    "Brigantine workshop in Tlaxcala — the siege machined into existence"),
    22: ("malintzin-translating.webp",  "Malintzin at the Tlaxcala council, late in the campaign"),
    26: ("bernardo-martyrdom.webp",     "Bernardo's martyrdom, Tlaxcalan chapel courtyard"),
}

def hero_image_block(chapter_n: int) -> str:
    pair = CHAPTER_HERO_IMAGE.get(chapter_n)
    if not pair:
        return ""
    fname, alt = pair
    safe_alt = alt.replace('"', "&quot;")
    return (
        '<p style="text-align:center;margin:0.5em 0 1.2em">'
        f'<img src="../assets/images/{fname}" alt="{safe_alt}" '
        'style="max-width:760px;width:100%;border-radius:4px;'
        'box-shadow:0 2px 8px rgba(0,0,0,0.25)">'
        f'<br><em style="font-size:0.9em;color:#666">{alt}</em>'
        '</p>\n\n'
    )


def feedback_form(page_id: str) -> str:
    """Inline HTML feedback form. POSTs to /feedback.json (a Worker URL
    configured in docs/_config.yml). On unconfigured deploys, the form
    falls back to a mailto:reader-feedback@laul.dev draft so visitors are
    never silently dropped. No GitHub account required."""
    safe = page_id.replace('"', "&quot;")
    return (
        '<form class="reader-feedback" data-page-id="' + safe + '" '
        'onsubmit="return submitReaderFeedback(event)">\n'
        '  <details>\n'
        '    <summary>💬 Send anonymous feedback on this page</summary>\n'
        '    <input type="hidden" name="chapter" value="' + safe + '">\n'
        '    <label>Kind:\n'
        '      <select name="kind">\n'
        '        <option>praise / what worked</option>\n'
        '        <option>critique / what did not work</option>\n'
        '        <option>factual or continuity error</option>\n'
        '        <option>voice / prose suggestion</option>\n'
        '        <option>bug or site issue</option>\n'
        '        <option>other</option>\n'
        '      </select>\n'
        '    </label><br>\n'
        '    <label>What you want to say:<br>\n'
        '      <textarea name="body" rows="6" cols="60" required></textarea>\n'
        '    </label><br>\n'
        '    <label>Optional contact (leave blank to stay anonymous):\n'
        '      <input type="text" name="contact" maxlength="200">\n'
        '    </label><br>\n'
        '    <button type="submit">Submit</button>\n'
        '    <span class="reader-feedback-status" aria-live="polite"></span>\n'
        '  </details>\n'
        '</form>'
    )

def build_nav(idx: int) -> str:
    n = nums[idx]
    parts = []
    if idx > 0:
        prev_n = nums[idx - 1]
        parts.append(f"[← Chapter {prev_n}](chapter_{prev_n:02d}.md)")
    parts.append("[Index](../index.md)")
    if idx < len(nums) - 1:
        next_n = nums[idx + 1]
        parts.append(f"[Chapter {next_n} →](chapter_{next_n:02d}.md)")
    nav_line = " · ".join(parts)
    form = feedback_form(f"Chapter {n}")
    return (
        NAV_DELIM + "\n\n---\n\n" + nav_line + "\n\n"
        + form + "\n\n"
        "{% include feedback-script.html %}\n"
    )

HERO_DELIM = "<!-- chapter-hero-injected -->"

for i, path in enumerate(ordered):
    text = path.read_text(encoding="utf-8")
    # Strip prior injected nav (idempotent re-runs).
    if NAV_DELIM in text:
        text = text.split(NAV_DELIM, 1)[0].rstrip() + "\n"
    # Strip prior injected hero image.
    if HERO_DELIM in text:
        before_marker, after_marker = text.split(HERO_DELIM + "\n", 1)
        # Drop the next block up to the next blank line + blank.
        after_lines = after_marker.split("\n", 1)[1] if "\n" in after_marker else ""
        # Simpler: split around the marker pair we emit.
        if HERO_DELIM in after_marker:
            tail = after_marker.split(HERO_DELIM + "\n", 1)[1]
            text = before_marker + tail
        else:
            text = before_marker
    # Inject hero image after the YAML frontmatter (between the second `---` and prose).
    n = nums[i]
    hero = hero_image_block(n)
    if hero:
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                fm = "---" + parts[1] + "---\n"
                body = parts[2].lstrip("\n")
                text = (
                    fm
                    + "\n"
                    + HERO_DELIM
                    + "\n"
                    + hero
                    + HERO_DELIM
                    + "\n\n"
                    + body
                )
        else:
            text = HERO_DELIM + "\n" + hero + HERO_DELIM + "\n\n" + text
    nav = build_nav(i)
    path.write_text(text.rstrip() + "\n\n" + nav, encoding="utf-8")
print(f"chapter nav injected on {len(ordered)} files")
PYEOF

# Inject feedback form at end of each retrospective.
python3 - "$DOCS/retrospectives" <<'PYEOF'
import re, sys
from pathlib import Path

retros_dir = Path(sys.argv[1])
files = sorted(retros_dir.glob("chapter_*.md"))
NAV_DELIM = "<!-- chapter-nav-injected -->"

def form_for(page_id: str) -> str:
    safe = page_id.replace('"', "&quot;")
    return (
        '<form class="reader-feedback" data-page-id="' + safe + '" '
        'onsubmit="return submitReaderFeedback(event)">\n'
        '  <details>\n'
        '    <summary>💬 Send anonymous feedback on this page</summary>\n'
        '    <input type="hidden" name="chapter" value="' + safe + '">\n'
        '    <label>Kind:\n'
        '      <select name="kind">\n'
        '        <option>praise / what worked</option>\n'
        '        <option>critique / what did not work</option>\n'
        '        <option>factual or continuity error</option>\n'
        '        <option>voice / prose suggestion</option>\n'
        '        <option>bug or site issue</option>\n'
        '        <option>other</option>\n'
        '      </select>\n'
        '    </label><br>\n'
        '    <label>What you want to say:<br>\n'
        '      <textarea name="body" rows="6" cols="60" required></textarea>\n'
        '    </label><br>\n'
        '    <label>Optional contact (leave blank to stay anonymous):\n'
        '      <input type="text" name="contact" maxlength="200">\n'
        '    </label><br>\n'
        '    <button type="submit">Submit</button>\n'
        '    <span class="reader-feedback-status" aria-live="polite"></span>\n'
        '  </details>\n'
        '</form>'
    )

for path in files:
    m = re.match(r"chapter_(\d+)\.md", path.name)
    if not m:
        continue
    n = int(m.group(1))
    text = path.read_text(encoding="utf-8")
    if NAV_DELIM in text:
        text = text.split(NAV_DELIM, 1)[0].rstrip() + "\n"
    page_id = f"Chapter {n} retrospective"
    block = (
        f"{NAV_DELIM}\n\n---\n\n"
        f"[Index](../index.md) · "
        f"[Chapter {n} canon](../chapters/chapter_{n:02d}.md)\n\n"
        + form_for(page_id) + "\n\n"
        "{% include feedback-script.html %}\n"
    )
    path.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
print(f"feedback form injected on {len(files)} retrospectives")
PYEOF

echo "staged:"
echo "  chapters:       $(ls "$DOCS/chapters" 2>/dev/null | wc -l) files"
echo "  retrospectives: $(ls "$DOCS/retrospectives" 2>/dev/null | wc -l) files"

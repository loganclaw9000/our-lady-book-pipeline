#!/usr/bin/env python3
"""Build a single downloadable PDF of the novel.

Concatenates canon/chapter_*.md, embeds hero images at chapter heads,
renders cover + ToC + chapter pages, writes
docs/our_lady_of_champion.pdf.

Run via:
    /tmp/pdfvenv/bin/python scripts/build_pdf.py
or any venv with markdown + weasyprint installed.
"""
from __future__ import annotations

import re
from datetime import datetime, UTC
from pathlib import Path

import markdown as md_lib
from weasyprint import HTML, CSS

ROOT = Path(__file__).resolve().parent.parent
CANON_DIR = ROOT / "canon"
IMG_DIR = ROOT / "docs" / "assets" / "images"
OUT_PDF = ROOT / "docs" / "our_lady_of_champion.pdf"

# Chapter → hero image (slug, alt). Mirrors render_reader.sh.
CHAPTER_HERO = {
    1:  ("cover-la-nina.webp", "La Niña de Córdoba on the Veracruz quay"),
    8:  ("cholula-courtyard.webp", "Cholula courtyard, dawn"),
    10: ("huitzilopochtli-engine.webp", "A Huitzilopochtli engine at the Templo Mayor"),
    14: ("great-engine-sleeping.webp", "The dormant Quetzalcoatl Great Engine"),
    17: ("noche-triste.webp", "La Noche Triste — Tlacopan causeway"),
    19: ("brigantine-workshop.webp", "Brigantine workshop in Tlaxcala"),
    22: ("malintzin-translating.webp", "Malintzin at the Tlaxcala council"),
    26: ("bernardo-martyrdom.webp", "Bernardo's martyrdom"),
}


def strip_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) — naive YAML strip; we only need word_count."""
    meta = {}
    if not text.startswith("---\n"):
        return meta, text
    rest = text[4:]
    if "\n---\n" not in rest:
        return meta, text
    fm_text, body = rest.split("\n---\n", 1)
    for line in fm_text.splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, body.lstrip("\n")


def chapter_num_from_path(p: Path) -> int:
    m = re.match(r"chapter_(\d+)\.md", p.name)
    if not m:
        raise ValueError(f"bad chapter file: {p.name}")
    return int(m.group(1))


def build_html() -> str:
    chapters = sorted(CANON_DIR.glob("chapter_*.md"), key=chapter_num_from_path)
    if not chapters:
        raise SystemExit("no canon chapters found")

    md = md_lib.Markdown(extensions=["extra", "smarty"])

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    cover_img = (IMG_DIR / "cover-la-nina.webp").as_uri()

    parts: list[str] = []

    # --- Cover page ---
    parts.append(f"""
<section class="cover">
  <img src="{cover_img}" alt="La Niña de Córdoba on the Veracruz quay">
  <h1 class="cover-title">Our Lady of Champion</h1>
  <p class="cover-subtitle">An autonomous-pipeline first-draft novel</p>
  <p class="cover-meta">
    16th-century Atlantic triangle.<br>
    Three POVs. Reliquaries and Teōmecahuītlī.<br>
    <small>Built {today}. {len(chapters)} chapters.</small>
  </p>
</section>
""")

    # --- Table of contents ---
    parts.append('<section class="toc"><h1>Contents</h1><ul>')
    chapter_data = []
    for path in chapters:
        n = chapter_num_from_path(path)
        text = path.read_text(encoding="utf-8")
        _, body = strip_frontmatter(text)
        wc = len(body.split())
        chapter_data.append((n, body, wc))
        parts.append(f'<li><span class="toc-num">Chapter {n}</span> '
                     f'<span class="toc-dots"></span> '
                     f'<span class="toc-wc">{wc:,}w</span></li>')
    total_w = sum(wc for _, _, wc in chapter_data)
    parts.append(f'</ul><p class="toc-total">{total_w:,} words total · {total_w // 250} pages @ 250w/pg</p></section>')

    # --- Chapters ---
    for n, body, wc in chapter_data:
        parts.append('<section class="chapter">')
        parts.append(f'<h1 class="chapter-num">Chapter {n}</h1>')
        if n in CHAPTER_HERO:
            slug, alt = CHAPTER_HERO[n]
            img_path = IMG_DIR / slug
            if img_path.exists():
                parts.append(
                    f'<figure class="chapter-hero">'
                    f'<img src="{img_path.as_uri()}" alt="{alt}">'
                    f'<figcaption>{alt}</figcaption>'
                    f'</figure>'
                )
        # Strip the per-scene HTML comment markers — they look noisy in print.
        clean_body = re.sub(r'<!--\s*scene:.*?-->\n?', '', body)
        # Render scene separators (---) as a small ornament for print.
        clean_body = re.sub(r'^---$', '<div class="scene-break">⁂</div>', clean_body, flags=re.MULTILINE)
        parts.append(md.convert(clean_body))
        parts.append('</section>')

    # --- Colophon ---
    parts.append(f"""
<section class="colophon">
  <h1>Colophon</h1>
  <p>This volume is a first-draft work-in-progress produced by an autonomous
  pipeline orchestrating a fine-tuned local voice model (paul-v7d-qwen35-27b)
  with a frontier-model critic (Claude Opus 4.7) under a 13-axis rubric over
  RAG-retrieved lore-bible context.</p>
  <p>Built {today} · {len(chapters)} chapters · {total_w:,} words.<br>
  Source: <a href="https://github.com/loganclaw9000/our-lady-book-pipeline">github.com/loganclaw9000/our-lady-book-pipeline</a></p>
</section>
""")

    css = """
@page {
  size: 6in 9in;
  margin: 0.7in 0.6in 0.8in 0.6in;
  @bottom-center {
    content: counter(page);
    font-family: 'Georgia', serif;
    font-size: 9pt;
    color: #666;
  }
}
@page :first { @bottom-center { content: ""; } }
@page cover { margin: 0; @bottom-center { content: ""; } }
@page toc   { @bottom-center { content: ""; } }
body {
  font-family: 'Georgia', 'Times New Roman', serif;
  font-size: 11pt;
  line-height: 1.55;
  color: #1a1a1a;
  text-align: justify;
  hyphens: auto;
}
section.cover {
  page: cover;
  page-break-after: always;
  text-align: center;
  height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: #14161a;
  color: #f5f5f5;
  padding: 0.8in;
}
section.cover img {
  max-width: 70%;
  margin: 0 auto 0.5in;
  border: 2px solid #c9a76b;
}
.cover-title {
  font-size: 28pt;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin: 0 0 0.2em;
  color: #f5e6c7;
}
.cover-subtitle {
  font-style: italic;
  font-size: 13pt;
  color: #c9a76b;
  margin: 0 0 1em;
}
.cover-meta { font-size: 11pt; line-height: 1.7; color: #ccc; }
.cover-meta small { color: #888; }

section.toc {
  page: toc;
  page-break-after: always;
}
section.toc h1 {
  font-size: 22pt;
  margin-bottom: 1em;
  border-bottom: 1px solid #888;
  padding-bottom: 0.3em;
}
section.toc ul { list-style: none; padding: 0; }
section.toc li {
  display: flex;
  align-items: baseline;
  margin: 0.4em 0;
  font-size: 11pt;
}
.toc-num { font-weight: 600; }
.toc-dots {
  flex: 1;
  border-bottom: 1px dotted #aaa;
  margin: 0 0.4em;
  height: 0.7em;
}
.toc-wc { color: #666; font-size: 10pt; }
.toc-total {
  margin-top: 1.5em;
  font-style: italic;
  font-size: 10pt;
  color: #666;
  text-align: center;
}

section.chapter {
  page-break-before: always;
}
.chapter-num {
  font-size: 24pt;
  text-align: center;
  margin: 0.4em 0 0.8em;
  font-variant: small-caps;
  letter-spacing: 0.06em;
  color: #4a3520;
}
.chapter-hero {
  margin: 0 auto 1em;
  text-align: center;
  page-break-inside: avoid;
}
.chapter-hero img {
  max-width: 4.6in;
  border: 1px solid #888;
  border-radius: 3px;
}
.chapter-hero figcaption {
  font-size: 9pt;
  font-style: italic;
  color: #666;
  margin-top: 0.4em;
}
section.chapter p {
  margin: 0 0 0.6em;
  text-indent: 1.4em;
}
section.chapter p:first-of-type { text-indent: 0; }
.scene-break {
  text-align: center;
  margin: 1.2em 0;
  font-size: 14pt;
  color: #888;
  letter-spacing: 0.5em;
}

section.colophon {
  page-break-before: always;
  font-size: 10pt;
  color: #444;
  text-align: center;
  margin-top: 2em;
}
section.colophon h1 {
  font-size: 18pt;
  font-variant: small-caps;
  letter-spacing: 0.06em;
  margin-bottom: 1em;
}
section.colophon p { text-align: center; line-height: 1.6; }
section.colophon a { color: #336; }
"""

    html_doc = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Our Lady of Champion</title></head><body>'
        + "\n".join(parts)
        + '</body></html>'
    )
    return html_doc, css


def main() -> None:
    print("[pdf] building HTML...")
    html_str, css_str = build_html()
    print(f"[pdf] HTML size: {len(html_str):,} chars")
    print("[pdf] rendering PDF (this takes ~30s for 24 chapters)...")
    HTML(string=html_str, base_url=str(ROOT)).write_pdf(
        str(OUT_PDF), stylesheets=[CSS(string=css_str)]
    )
    size_mb = OUT_PDF.stat().st_size / (1024 * 1024)
    print(f"[pdf] wrote {OUT_PDF} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

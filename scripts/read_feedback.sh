#!/usr/bin/env bash
# read_feedback.sh — pull reader feedback issues from GitHub and write to
# .planning/feedback/ for the autonomous agent (and operator) to review.
#
# Usage:
#   scripts/read_feedback.sh          # pull all open feedback issues
#   scripts/read_feedback.sh --closed # include closed
#   scripts/read_feedback.sh --since 2026-04-01
#
# Output:
#   .planning/feedback/FEEDBACK.md      — human-readable digest
#   .planning/feedback/feedback.jsonl  — machine-readable line per issue
#
# The agent's auto-memory system pulls from .planning/feedback/FEEDBACK.md
# at session start; this script is the bridge from public-facing reader
# feedback (gh issues) into the project knowledge base.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/.planning/feedback"
mkdir -p "$OUT_DIR"

STATE="open"
SINCE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --closed) STATE="all"; shift ;;
        --since)  SINCE="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Pull issues with the 'feedback' label.
GH_ARGS=(issue list --label feedback --state "$STATE" --limit 200 --json number,title,body,createdAt,closedAt,state,author,labels,url)
if [[ -n "$SINCE" ]]; then
    GH_ARGS+=(--search "created:>=$SINCE")
fi
RAW_JSON="$(gh "${GH_ARGS[@]}" 2>/dev/null || echo '[]')"

# Write JSONL (one issue per line) and Markdown digest.
python3 - "$OUT_DIR" "$RAW_JSON" <<'PYEOF'
import json, sys
from pathlib import Path

out_dir = Path(sys.argv[1])
issues = json.loads(sys.argv[2])

# JSONL.
jsonl_path = out_dir / "feedback.jsonl"
with jsonl_path.open("w", encoding="utf-8") as f:
    for issue in issues:
        f.write(json.dumps(issue, ensure_ascii=False) + "\n")

# Markdown digest.
digest_path = out_dir / "FEEDBACK.md"
lines = ["# Reader feedback digest", ""]
lines.append(f"_pulled {len(issues)} issues from GitHub feedback queue. Source: gh issue list --label feedback._")
lines.append("")
if not issues:
    lines.append("No feedback issues yet.")
else:
    by_chapter: dict[str, list] = {}
    for issue in issues:
        body = issue.get("body") or ""
        # Issue Form bodies have ### Chapter\nValue\n etc. Try to parse "Chapter" field.
        chapter = "general"
        for marker in ("### Chapter", "**Chapter**"):
            if marker in body:
                chunk = body.split(marker, 1)[1].split("###", 1)[0]
                cand = chunk.strip().split("\n")[0].strip()
                if cand and cand != "_No response_":
                    chapter = cand
                    break
        by_chapter.setdefault(chapter, []).append(issue)

    for chapter in sorted(by_chapter):
        lines.append(f"## {chapter}")
        lines.append("")
        for issue in by_chapter[chapter]:
            num = issue.get("number")
            title = issue.get("title", "(no title)")
            state = issue.get("state", "?")
            url = issue.get("url", "")
            created = issue.get("createdAt", "")[:10]
            author_obj = issue.get("author") or {}
            author = author_obj.get("login", "?")
            lines.append(f"- **#{num}** [{title}]({url}) — `{state}` · {created} · @{author}")
            body = (issue.get("body") or "").strip()
            if body:
                # Indent body by 2 spaces; trim noisy delimiters.
                trimmed = "\n".join("  > " + ln for ln in body.splitlines() if ln.strip())
                lines.append(trimmed)
            lines.append("")

digest_path.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote: {digest_path}")
print(f"wrote: {jsonl_path}")
print(f"issues: {len(issues)}")
PYEOF

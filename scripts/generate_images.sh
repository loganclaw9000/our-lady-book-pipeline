#!/usr/bin/env bash
# generate_images.sh — call Stability AI to render hero-moment images
# for the reader site. Saves WebP to docs/assets/images/.
#
# Requires: STABILITY_API_KEY env var.
# Default endpoint: ultra (8 credits / image, top quality).
# Override via ENDPOINT=core (3c) or ENDPOINT=sd3 (6.5c).
set -euo pipefail

: "${STABILITY_API_KEY:?STABILITY_API_KEY env var required}"
ENDPOINT="${ENDPOINT:-ultra}"
URL="https://api.stability.ai/v2beta/stable-image/generate/${ENDPOINT}"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docs/assets/images"
mkdir -p "$OUT_DIR"

# 1=slug, 2=aspect, 3=prompt, 4=neg
gen() {
    local slug="$1" aspect="$2" prompt="$3" neg="${4:-}"
    local out="$OUT_DIR/${slug}.webp"
    if [[ -f "$out" ]] && [[ "${REGEN:-0}" != "1" ]]; then
        echo "[gen] skip (exists): $slug"
        return 0
    fi
    echo "[gen] $slug ($aspect) -> $out"
    local rc
    if [[ -n "$neg" ]]; then
        curl -sS -f -X POST "$URL" \
            -H "Authorization: Bearer $STABILITY_API_KEY" \
            -H "Accept: image/*" \
            -F "prompt=$prompt" \
            -F "negative_prompt=$neg" \
            -F "aspect_ratio=$aspect" \
            -F "output_format=webp" \
            -o "$out"
        rc=$?
    else
        curl -sS -f -X POST "$URL" \
            -H "Authorization: Bearer $STABILITY_API_KEY" \
            -H "Accept: image/*" \
            -F "prompt=$prompt" \
            -F "aspect_ratio=$aspect" \
            -F "output_format=webp" \
            -o "$out"
        rc=$?
    fi
    if [[ $rc -ne 0 ]]; then
        echo "[gen] FAIL $slug rc=$rc"
        return 1
    fi
    local size
    size=$(stat -c %s "$out")
    echo "[gen] ok $slug · ${size} bytes"
}

NEG="cartoon, anime, low quality, deformed, watermark, text, signature, modern clothing, photographic stock"

# Painterly style anchor to keep all images cohesive.
STYLE="oil painting, painterly historical-fiction illustration, dramatic chiaroscuro, muted earth palette with warm gold accents, fine brushwork, cinematic composition, Diego Rivera mural meets Goya, dark fantasy book cover quality"

# 1 — Cover hero: La Niña de Córdoba on Veracruz quay
gen "cover-la-nina" "2:3" \
"A 50-foot gilded reliquary war engine in human shape standing on a wooden quay at dusk, ornate gold plate armor in the style of 16th century Spanish smithing covered with Catholic saint imagery, a softly glowing crystal monstrance set into its chest containing the small bones of a child martyr, the engine quiet and patient like a sleeping cathedral, harbor lanterns reflecting on Caribbean water, Havana 1518, $STYLE" \
"$NEG"

# 2 — Mexica engine: Huitzilopochtli warrior-engine
gen "huitzilopochtli-engine" "4:5" \
"A 60-foot Mexica war engine shaped like an armored hummingbird-warrior god, vivid solar heraldry, obsidian and feather inlay, blue-paint warrior glyphs, crouched in the courtyard of the Templo Mayor at midday, Tenochtitlan 1519, the sun blazing on its plumed helm, immense scale dwarfing the priests around it, sacred geometry incised on its limbs, $STYLE" \
"$NEG"

# 3 — Cholula massacre Reliquaries
gen "cholula-courtyard" "16:9" \
"Dawn light in a Mesoamerican stone courtyard between a great pyramid and lesser shrines, pale flagstone like wet bone, four 50-foot Spanish reliquary engines standing in their wooden cradles each holding a polearm, Mexica noblemen in elaborate feathered cloaks falling under arquebus volley, the engines just beginning to move, Cholula October 1519, witnessed atrocity rendered with restraint, $STYLE" \
"$NEG"

# 4 — La Noche Triste
gen "noche-triste" "16:9" \
"Midnight cold rain on the Tlacopan causeway, a column of Spanish reliquary war engines walking single file across the lake, torches sputtering thirty yards apart, Mexica war canoes circling in the dark water beyond the torchlight with bowmen drawing back, gold gleaming on the engines making them slow, Tenochtitlan retreat June 1520, dread and fatigue, $STYLE" \
"$NEG"

# 5 — Bernardo's martyrdom
gen "bernardo-martyrdom" "4:5" \
"Twilight in a small Tlaxcalan chapel courtyard, a Franciscan friar in coarse brown robes kneeling, his hands bound with his own knotted cord at his instruction, candle flame reflecting on stone, witnessed by a small ring of soldiers and a single woman with a Nahuatl primer in her hand, ritualized, sacred, terrible, no gore visible, the moment before the act, 1521, $STYLE" \
"$NEG"

# 6 — Great Engine sleeping
gen "great-engine-sleeping" "16:9" \
"An immense dormant Mexica war engine in the form of a feathered serpent god Quetzalcoatl, head wider than a temple courtyard, resting muzzle on coiled forelimbs like a sleeping dog, set inside the Templo Mayor sacred enclosure, dust motes in shafts of sunlight, scale of architecture visible alongside, no humans for scale rendering, Tenochtitlan 1519, $STYLE" \
"$NEG"

# 7 — Malintzin at Tlaxcala council
gen "malintzin-translating" "4:5" \
"A young Nahua woman in her late teens standing beside a Spanish council table in a Tlaxcalan longhouse, candlelit, drawing a primer on parchment, six months pregnant rendered with dignity not exoticism, Spanish captains and Tlaxcalan elders around her in posture of listening, a half-finished map and gourd cups on the table, 1521, $STYLE" \
"$NEG"

# 8 — Brigantine workshop
gen "brigantine-workshop" "16:9" \
"Interior of a long Tlaxcalan workshop spanning three knocked-out houses, ribs and hull-pieces of thirteen river-going brigantines being shaped and labeled with chalk, Tlaxcalan carpenters working alongside Spanish woodsmen, sawdust in shafts of cloud-light from a high window, the great pass of the volcanoes visible through the doorway, machinery of inevitability quietly assembled, 1521, $STYLE" \
"$NEG"

# Final balance
echo
echo "=== Stability balance ==="
curl -sS -H "Authorization: Bearer $STABILITY_API_KEY" \
  https://api.stability.ai/v1/user/balance | python3 -m json.tool

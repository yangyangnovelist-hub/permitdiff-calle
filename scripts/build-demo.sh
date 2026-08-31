#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for cmd in node npm uv ffmpeg ffprobe curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

if [ ! -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  echo "Google Chrome was not found at the expected macOS path." >&2
  exit 1
fi

curl -fsS "${PERMITDIFF_DEMO_URL:-https://permitdiff.vercel.app/}" >/dev/null
curl -fsS "${PERMITDIFF_EVIDENCE_URL:-https://yangyangnovelist-hub.github.io/permitdiff-calle/}" >/dev/null
mkdir -p video/build/browser

if [ ! -d node_modules/playwright ]; then
  echo "Installing Playwright locally without changing project metadata..."
  npm install --no-save --no-package-lock playwright
fi

BEFORE_LIST="$(mktemp)"
AFTER_LIST="$(mktemp)"
find video/build/browser -type f -name '*.webm' -print | sort > "$BEFORE_LIST"
node scripts/record-demo.mjs
find video/build/browser -type f -name '*.webm' -print | sort > "$AFTER_LIST"
VIDEO="$(comm -13 "$BEFORE_LIST" "$AFTER_LIST" | tail -n 1)"
rm -f "$BEFORE_LIST" "$AFTER_LIST"

if [ -z "${VIDEO:-}" ] || [ ! -f "$VIDEO" ]; then
  echo "Could not locate the newly recorded browser video." >&2
  exit 1
fi

uv run --script scripts/synthesize-demo-narration.py

NARRATION="video/build/narration-kokoro.wav"
SRT="video/permitdiff-demo.en.srt"
OUTPUT="video/build/permitdiff-demo.mp4"

if ffmpeg -hide_banner -filters 2>/dev/null | grep -qE '[[:space:]]subtitles[[:space:]]'; then
  ffmpeg -y \
    -i "$VIDEO" \
    -i "$NARRATION" \
    -vf "subtitles=filename='${SRT}':force_style='FontName=Arial,FontSize=18,Outline=1,Shadow=0,MarginV=24'" \
    -map 0:v:0 \
    -map 1:a:0 \
    -c:v libx264 \
    -preset medium \
    -crf 20 \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 160k \
    -movflags +faststart \
    -shortest \
    "$OUTPUT"
else
  ffmpeg -y \
    -i "$VIDEO" \
    -i "$NARRATION" \
    -i "$SRT" \
    -map 0:v:0 \
    -map 1:a:0 \
    -map 2:0 \
    -c:v libx264 \
    -preset medium \
    -crf 20 \
    -pix_fmt yuv420p \
    -c:a aac \
    -b:a 160k \
    -c:s mov_text \
    -metadata:s:s:0 language=eng \
    -disposition:s:0 default \
    -movflags +faststart \
    -shortest \
    "$OUTPUT"
fi

DURATION="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUTPUT")"
echo "Built: $OUTPUT"
printf 'Duration: %.1f seconds\n' "$DURATION"
echo "The recording uses deterministic reviewer modes and cannot place a phone call."

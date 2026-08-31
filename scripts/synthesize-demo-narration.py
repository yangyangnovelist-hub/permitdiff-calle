# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "en-core-web-sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
#   "kokoro==0.9.4",
#   "librosa==1.0.0",
#   "soundfile==0.14.0",
# ]
# ///
"""Build subtitle-timed narration with Apache-2.0 Kokoro-82M."""

from __future__ import annotations

import re
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from kokoro import KPipeline

ROOT = Path(__file__).resolve().parents[1]
SRT_PATH = ROOT / "video" / "permitdiff-demo.en.srt"
OUTPUT_PATH = ROOT / "video" / "build" / "narration-kokoro.wav"
CACHE_DIR = OUTPUT_PATH.parent / "kokoro-bm-george-120-cues"
TIMING_PATTERN = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)
SAMPLE_RATE = 24_000


def seconds(parts: tuple[str, str, str, str]) -> float:
    hours, minutes, secs, millis = map(int, parts)
    return hours * 3600 + minutes * 60 + secs + millis / 1000


def parse_srt(path: Path) -> list[tuple[int, float, float, str]]:
    cues: list[tuple[int, float, float, str]] = []
    for block in path.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = block.splitlines()
        match = TIMING_PATTERN.fullmatch(lines[1])
        if match is None:
            raise ValueError(f"Invalid cue timing: {lines[1]}")
        cues.append(
            (
                int(lines[0]),
                seconds(match.groups()[:4]),
                seconds(match.groups()[4:]),
                " ".join(lines[2:]),
            )
        )
    return cues


def fit_cue(speech: np.ndarray, available: float) -> np.ndarray:
    rate = max(1.0, (len(speech) / SAMPLE_RATE) / available)
    if rate > 1.0:
        speech = librosa.effects.time_stretch(speech, rate=rate)
    return speech[: int(available * SAMPLE_RATE)]


def finish_cue(speech: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(speech))) if len(speech) else 0.0
    if peak > 0:
        speech = speech * min(0.90 / peak, 1.4)
    fade_samples = min(int(0.025 * SAMPLE_RATE), len(speech) // 2)
    if fade_samples:
        fade = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
        speech[:fade_samples] *= fade
        speech[-fade_samples:] *= fade[::-1]
    return speech


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pipeline = KPipeline(lang_code="b", repo_id="hexgrad/Kokoro-82M", device="cpu")
    cues = parse_srt(SRT_PATH)
    timeline = np.zeros(int((cues[-1][2] + 0.35) * SAMPLE_RATE), dtype=np.float32)

    for cue_number, start, end, text in cues:
        cue_path = CACHE_DIR / f"{cue_number:02d}.wav"
        if cue_path.exists():
            speech, existing_rate = sf.read(cue_path, dtype="float32")
            if existing_rate != SAMPLE_RATE:
                speech = librosa.resample(
                    speech, orig_sr=existing_rate, target_sr=SAMPLE_RATE
                )
        else:
            pieces = [
                result.audio.detach().cpu().numpy()
                for result in pipeline(text, voice="bm_george", speed=1.20)
                if result.audio is not None
            ]
            if not pieces:
                raise RuntimeError(f"No audio generated for cue {cue_number}")
            speech = np.concatenate(pieces).astype(np.float32)
            speech, _ = librosa.effects.trim(speech, top_db=42)
            sf.write(cue_path, speech, SAMPLE_RATE, subtype="PCM_24")

        speech = finish_cue(fit_cue(speech, end - start - 0.10))
        offset = int(start * SAMPLE_RATE)
        timeline[offset : offset + len(speech)] += speech

    sf.write(OUTPUT_PATH, timeline, SAMPLE_RATE, subtype="PCM_24")
    print(f"Wrote {OUTPUT_PATH} ({len(timeline) / SAMPLE_RATE:.2f}s)")


if __name__ == "__main__":
    main()

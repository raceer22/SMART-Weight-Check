"""When each word is spoken in the voice clips → scripts/video/words.json (used by timeline.py).

The video times its captions, text animations, camera moves and sound effects to these words, so re-run this
after regenerating a clip. It needs faster-whisper, which wants Python ≤ 3.12 (not the project venv):

    uv venv --python 3.12 /tmp/whisper && VIRTUAL_ENV=/tmp/whisper uv pip install faster-whisper
    FFMPEG=/path/to/ffmpeg /tmp/whisper/bin/python scripts/video/words.py

Whisper's word times are good to about 0.1 s, except around numbers ("three hundred and forty-six" becomes "346"
and can land late). Caption start times therefore stay in timeline.CAPTIONS, measured with silencedetect.
"""
import json
import os
import subprocess
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

VIDEO = Path(__file__).resolve().parent
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def load(path: Path) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def main() -> None:
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    out = {}
    for n in range(1, 9):
        segments, _ = model.transcribe(load(VIDEO / "audio" / f"{n:02d}.mp3"), word_timestamps=True, beam_size=5,
                                       language="en")
        out[str(n)] = [[round(w.start, 2), round(w.end, 2), w.word.strip()] for s in segments for w in s.words]
        print(n, " ".join(f"{w}@{a:.2f}" for a, _, w in out[str(n)]), flush=True)
    lines = ",\n".join(f' "{k}": [' + ", ".join(json.dumps(w, ensure_ascii=False) for w in v) + "]" for k, v in out.items())
    (VIDEO / "words.json").write_text("{\n" + lines + "\n}\n")


if __name__ == "__main__":
    main()

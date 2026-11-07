"""Timing of the peer-vote video: voice clips, pauses, captions, spoken words. Shared by make_assets.py and build_video.py.

Caption start times come from ffmpeg silencedetect on the ElevenLabs clips (pauses between sentences); the time of
every word comes from words.json (words.py, faster-whisper). Camera moves, text animations and sound effects are
cued to words with cue(), so they follow a regenerated clip. If a clip is regenerated, re-measure both:
    ffmpeg -i submission/video/audio/05.mp3 -af silencedetect=noise=-40dB:d=0.15 -f null -
    python submission/video/words.py          (see its docstring for the faster-whisper setup)
"""
import difflib
import json
import re
from pathlib import Path

VIDEO = Path(__file__).resolve().parent
AUDIO = VIDEO / "audio"
BUILD = VIDEO / "build"
ASSETS = BUILD / "assets"

W, H, FPS = 1920, 1080, 30
LEAD = 0.6        # the chart fades in from its blank background before the first word
GAP = 0.5         # silence between scenes (each clip also ends with ~0.2 s of its own)
END_HOLD = 3.0    # end card after the last word

# scene clip lengths in seconds (ffprobe)
CLIP_LEN = {1: 16.80, 2: 10.32, 3: 11.92, 4: 10.88, 5: 15.60, 6: 11.36, 7: 14.00, 8: 12.56}

START = {}
_t = LEAD
for _n in range(1, 9):
    START[_n] = round(_t, 3)
    _t += CLIP_LEN[_n] + GAP
VOICE_END = START[8] + CLIP_LEN[8]
TOTAL = round(VOICE_END + END_HOLD, 3)

# captions per scene: (seconds into the clip, text). Each one shows until the next one (or the clip end).
CAPTIONS = {
    1: [(0.00, "In July, a compactor in Lohja had a problem:"),
        (3.65, "its fill sensor was stuck at 88 %,"),
        (6.75, "even though the scale showed it was nearly empty."),
        (9.65, "Four trucks came anyway."),
        (11.71, "The wasted trips cost €346 —"),
        (15.42, "and no one noticed.")],
    2: [(0.00, "Businesses pay for waste by the lift and by the tonne."),
        (4.02, "But the only scale they ever see belongs to their operator."),
        (7.83, "So we built SMART Weight Check.")],
    3: [(0.00, "An independent scale inside the Europress compactor weighs every lift."),
        (5.15, "Our software checks it against the invoice and the contract,"),
        (8.51, "and turns each difference into a decision you control.")],
    4: [(0.00, "This is one customer: 25 compactors at 8 sites."),
        (4.87, "Every finding becomes a decision, ranked by the money at stake."),
        (9.25, "The biggest come first.")],
    5: [(0.00, "In Porvoo, a site was invoiced 2.94 tonnes."),
        (4.40, "Its container held 580 kilos."),
        (7.70, "Two containers shared a truck, and the weight was split in half."),
        (11.67, "The customer’s total is right."),
        (13.77, "This site’s share is not.")],
    6: [(0.00, "Tap “Why?”, and the proof is right there:"),
        (3.05, "the frozen sensor, the empty scale, every truck."),
        (6.88, "Approve sends it to your account manager,"),
        (9.07, "and every decision can be undone.")],
    # 7: times are placeholders until 07.mp3 is regenerated with the new line and re-measured
    7: [(0.00, "All of this starts with the scale: four load cells under the container."),
        (4.27, "Every time the container leaves, the scale resets to zero,"),
        (8.01, "so it stays accurate to within 3 %."),
        (11.21, "It costs €1,200, fitted in the factory.")],
    8: [(0.00, "The service: €15 per compactor per month."),
        (3.93, "In our model, the typical customer gets back more than twice that.")],
}
CAPTION_STOP = {8: 8.23}   # the end card carries its own words
AMOUNT_AT = 12.98          # clip 1: "three hundred and forty-six" starts (waveform; whisper says 12.86); the € counter rolls from here


WORDS = {int(k): v for k, v in json.loads((VIDEO / "words.json").read_text()).items()}


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def cue(scene: int, *words: str, n: int = 0) -> float:
    """Video time of the n-th spoken word that starts with `word` (the first of `words` found in the clip)."""
    for word in words:
        hits = [a for a, _, w in WORDS[scene] if norm(w).startswith(norm(word))]
        if len(hits) > n:
            return round(START[scene] + hits[n], 3)
    raise KeyError(f"scene {scene}: none of {words} is spoken (re-run words.py after regenerating a clip?)")


def caption_tokens():
    """For each caption of caption_spans(): [(word as shown, video time it is spoken)].

    Caption words are matched to the spoken words; numbers written differently ("2.94" vs "2", ".94") get times
    interpolated between their neighbours. Symbols such as "%" stick to the word before them."""
    out = []
    for scene, caps in CAPTIONS.items():
        end_scene = CLIP_LEN[scene] + 0.25
        for k, (t, text) in enumerate(caps):
            t_next = caps[k + 1][0] if k + 1 < len(caps) else end_scene
            toks = []
            for raw in text.split(" "):
                if toks and not norm(raw):
                    toks[-1] += " " + raw
                else:
                    toks.append(raw)
            spoken = [(a, w) for a, _, w in WORDS[scene] if t - 0.25 <= a < t_next - 0.25]
            times = [None] * len(toks)
            sm = difflib.SequenceMatcher(None, [norm(x) for x in toks], [norm(w) for _, w in spoken], autojunk=False)
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op in ("equal", "replace"):           # "2.94" → the first of "2", ".94"
                    for i in range(i1, i2):
                        times[i] = spoken[j1 + (i - i1) * (j2 - j1) // (i2 - i1)][0]
            times[0] = t
            for j in range(len(toks)):                   # words never heard: between their neighbours
                if times[j] is None:
                    nxt = next((i for i in range(j + 1, len(toks)) if times[i] is not None), None)
                    times[j] = (times[j - 1] + 0.3 if nxt is None
                                else times[j - 1] + (times[nxt] - times[j - 1]) / (nxt - j + 1))
            run = t
            for j in range(len(toks)):
                run = max(run, times[j])
                times[j] = run
            out.append([(tok, round(START[scene] + x, 3)) for tok, x in zip(toks, times)])
    return out


def caption_spans():
    """[(start, end, index, text)] in video time, one per caption image."""
    spans, i = [], 0
    for scene, caps in CAPTIONS.items():
        end_scene = START[scene] + CAPTION_STOP.get(scene, CLIP_LEN[scene] + 0.25)
        for k, (t, text) in enumerate(caps):
            a = START[scene] + t
            b = START[scene] + caps[k + 1][0] if k + 1 < len(caps) else end_scene
            spans.append((a, b, i, text))
            i += 1
    return spans

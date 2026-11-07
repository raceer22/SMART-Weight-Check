# Peer-vote video: script (2:00 hard limit)

Audio first: generate one ElevenLabs clip per scene, then the video is cut to the clips. 262 words, about 100–110 s of voice, plus pauses and a 3 s end card. All data is synthetic, which is shown as a caption in the opening shot and on the end card.

Paste the **voice line** exactly. Numbers are written as words so they are read correctly.

| # | voice line (paste this) | on screen | words |
|---|---|---|---|
| 1 | In July, a compactor in Lohja had a problem: its fill sensor was stuck at eighty-eight percent, even though the scale showed it was nearly empty. Four trucks came anyway. The wasted trips cost three hundred and forty-six euros—and no one noticed. | Cold open on the CMP-00046 charts: the fill line jumps to 88 % and stays flat, the weight line stays at zero, the four wasted trips appear one by one in amber. Big overlay: **€346 for nothing**. Caption: *All data is synthetic.* | 42 |
| 2 | Businesses pay for waste by the lift and by the tonne. But the only scale they ever see belongs to their operator. So we built SMART Weight Check. | Title card in Europress cyan: **SMART Weight Check** · Weigh at source. Check every tonne. | 28 |
| 3 | An independent scale inside the Europress compactor weighs every lift. Our software checks it against the invoice and the contract, and turns each difference into a decision you control. | Weigh-frame illustration, then three steps: Weigh → Check → Decide. | 29 |
| 4 | This is one customer: twenty-five compactors at eight sites. Every finding becomes a decision, ranked by the money at stake. The biggest come first. | App: the inbox opens. "40 decisions are waiting for you", €6,210 in question; slow scroll over the top cards. | 24 |
| 5 | In Porvoo, a site was invoiced two point nine four tonnes. Its container held five hundred and eighty kilos. Two containers shared a truck, and the weight was split in half. The customer's total is right. This site's share is not. | Zoom on the CMP-00042 card ("2.94 t", "580 kg"), then **Why?** opens the weight table. | 40 |
| 6 | Tap why, and the proof is right there: the frozen sensor, the empty scale, every truck. Approve sends it to your account manager, and every decision can be undone. | **Why?** on CMP-00046: the charts with the amber trips. Click **Approve**: tick sound, €346 jumps into "€ sent for review". Click **Undo**. | 29 |
| 7 | All of this starts with the scale: four load cells under the container. Every time the container leaves, the scale resets to zero, so it stays accurate to within three percent. It costs twelve hundred euros, fitted in the factory. | Weigh-frame card: 4 load cells · resets to zero · ±3 % · €1,200 factory / €3,400 retrofit. | 40 |
| 8 | The service is fifteen euros per compactor per month. In our model, the typical customer gets back more than twice that. SMART Weight Check. Weigh at source. Check every tonne. | Price card: €15 per compactor-month · median value €36 *(estimated)*. End card: SMART Weight Check · Weigh at source. Check every tonne. · *All data is synthetic. A concept for Europress SMART compactors.* | 30 |

## Where each claim comes from

| claim | source |
|---|---|
| fill froze at 88 %, scale 20–35 kg ("nearly empty"), 4 wasted trips, €346 | `notes/FINDINGS.md` C03 · app decision `CMP-00046 \| wasted` |
| 25 compactors at 8 sites, 40 decisions, €6,210 in question | the app on quickstart data (`app/inbox.py`, `tests/test_inbox.py`) |
| invoiced 2.94 t, container 580 kg, shared truck split equally | `notes/FINDINGS.md` (combined loads) · app decision `CMP-00042 \| resplit` |
| four load cells, zero check on every lift, €1,200 factory | `submission/1_WEIGHING_CONCEPT.md` |
| "within three percent": the σ 1.5 % design target, so about 95 % of loads land within ±3 % (2σ); on 3 t loads that is the doc's "97–98 % within ±100 kg" | `submission/1_WEIGHING_CONCEPT.md` |
| €15 per device-month, median value €36 (2.4× the fee, "in our model") | `submission/3_BUSINESS_CASE.md` |

## ElevenLabs settings

- **One voice and the same settings for all eight clips**, so they sound like one take. A calm, warm, mid-pitch English voice works best; keep speed at 1.0.
- **Pronunciation:** Lohja = "LOH-yah", Porvoo = "POR-voh". If the voice gets them wrong, write `Loh-yah` or `Por-voh` in the text box for that clip only.
- **Export** MP3 or WAV, 44.1 kHz, and name the files `01.mp3` … `08.mp3`.
- **Music:** about 2:10 of instrumental, calm, modern, minimal electronic, about 100 BPM, no vocals → `music.mp3`. It sits about 20 dB under the voice and fades out on the end card.
- **Sound effect:** one short, soft UI tick for the clicks → `tick.mp3`. The other effects are synthesised (see below).
- Put everything in `scripts/video/audio/` (ignored by git). Check that your ElevenLabs plan covers this use; the licence goes into `submission/THIRD_PARTY.md`.

## Sound effects

Synthesised by `sfx.py` (no samples): a low whoosh on each scene change, a lighter swish on the big camera moves only
(none within 1.5 s after another whoosh-type sound), quiet swooshes and pops as text and highlights come in, hits
for the €346 counter, "SMART Weight Check" and "€15", risers before the two title reveals, and the ElevenLabs click
on every tap. The whoosh-type sounds peak around 1–2 kHz, below the voice's consonants, and each comes in four
variants (pitch, length, noise) that rotate so no clip repeats back to back. `build_video.py` places them from the
shot list. To replace one with your own, put `audio/sfx_<name>.mp3` next to the voice clips (names: whoosh, swish,
swoosh, pop, impact, thump, riser, ticker); a replaced whoosh-type sound loses its variants. ElevenLabs Sound
Effects prompts that fit:

| file | prompt |
|---|---|
| `sfx_whoosh.mp3` | Deep, soft whoosh for a video scene transition, warm and low, no hiss, 0.6 seconds |
| `sfx_swish.mp3` | Very short soft swish of a camera move, subtle, mid-range, 0.3 seconds |
| `sfx_impact.mp3` | Deep cinematic logo hit, punchy, short tail, 1 second |
| `sfx_pop.mp3` | Soft UI pop, rounded, 0.15 seconds |

## Build the video

Audio clips, music and the tick go in `scripts/video/audio/` as `01.mp3` … `08.mp3`, `music.mp3`, `tick.mp3`.
Clip lengths and sentence starts (silencedetect) are in `timeline.py`; the time of every word is in `words.json`.
Re-measure both if a clip is regenerated (`words.py` needs faster-whisper, see its docstring).

```bash
streamlit run app/app.py --server.headless true                  # the app, for the stills
python scripts/video/make_assets.py http://localhost:8501      # app stills, chart, layered cards (~1 min)
FFMPEG=/path/to/ffmpeg-with-libx264 python scripts/video/build_video.py --out smart_weight_check
python scripts/video/build_video.py --stills 12.6,40.5         # single frames to check framing
python scripts/video/build_video.py --preview --out preview    # 960×540, 15 fps, to check timing
```

Output: `scripts/video/build/smart_weight_check.mp4`, 1920×1080, 30 fps, H.264 + AAC, 1:49.7. The video opens on
a blank background, so upload `build/smart_weight_check_thumbnail.png` (written by every full render: the finished July
chart with €346) as the thumbnail wherever the platform allows it. Without a libx264 build, `build_video.py` falls back to OpenH264 at 14 Mbit/s. The static ffmpeg from
`pip install imageio-ffmpeg` has libx264.

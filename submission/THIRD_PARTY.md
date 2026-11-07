# Third-party libraries, data, models and services

The brief asks us to identify every third-party library, model, dataset or service we used, its licence and any commercial-use restrictions. Versions are the ones installed in the development environment, read from each package's own metadata. *This is a list, not legal advice.*

## Dataset

| item | licence / terms | commercial-use notes |
|---|---|---|
| Europress × Since AI Hackathon 2026 synthetic dataset and generator, v1.0.1 (`data/`, `src/europress_data/`, `baselines/`, `docs/`, `examples/`, `tests/`) | no separate licence file; the README says use of the data and of team results follows the **Since AI Hackathon 2026 rules** | entirely synthetic, no personal data; prices are hypothetical. Check the event rules before any use outside the hackathon |

Our own work on top of it: `app/`, `.streamlit/`, `notes/`, `configs/our_params.yaml`, `our_business_case/`, `scripts/app_screenshots.py`, `scripts/deck/`, `scripts/video/`, `tests/test_inbox.py`, `submission/`.

## Python libraries (runtime and analysis)

| library | version | licence | used for |
|---|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause (bundled parts: 0BSD, MIT, Zlib, CC0-1.0) | arrays |
| pandas | 3.1.1 | BSD-3-Clause | tables |
| pyarrow | 26.0.1 | Apache-2.0 | Parquet files |
| duckdb | 2.0.0 | MIT | SQL over the Parquet files |
| PyYAML | 6.0.3 | MIT | parameter files |
| pytz | 2026.6 | MIT | time zones |
| tabulate | 0.10.0 | MIT | Markdown tables |
| streamlit | 1.67.0 | Apache-2.0 | demo app |
| altair (Vega-Altair, renders with Vega-Lite) | 6.3.0 | BSD-3-Clause | app charts |
| matplotlib | 3.11.2 | Matplotlib licence (PSF-based, BSD-compatible) | analysis charts |
| scikit-learn | 1.9.1 | BSD-3-Clause | gradient boosting in the no-scale weight experiments |
| pytest | 9.2.0 | MIT | the dataset package's tests |
| Markdown | 3.11.3 | BSD-3-Clause | docs build of the dataset package |

All of these are permissive licences that allow commercial use. Apache-2.0 asks you to keep its NOTICE and licence text when redistributing; BSD and MIT ask you to keep the copyright notice.

## Font and look

| item | licence / terms | used for |
|---|---|---|
| Poppins (Indian Type Foundry), loaded from Google Fonts | SIL Open Font License 1.1: free for commercial use | app and deck typeface |
| Brand colour `#03b4e0` | read from the public stylesheet of europressgroup.com | the app's accent colour, so the concept looks at home next to Europress SMART. No Europress logo, image or other trademark is used, and the app says "A concept for Europress SMART compactors" |

## Tools used only to produce submission files (not needed to run the demo)

| tool | licence | used for |
|---|---|---|
| PptxGenJS 3.12.0 (Node.js) | MIT | building the pitch deck (`scripts/deck/build_deck.js`) |
| react-icons 5.4.0 · React / ReactDOM 18.3.1 · sharp 0.33.5 | MIT (icons: Font Awesome Free icons, CC BY 4.0) · MIT · Apache-2.0 | the three icons on slide 3 |
| LibreOffice | MPL-2.0 | exporting the deck to PDF |
| Playwright 1.64.1 (Python) with Chromium headless shell | Apache-2.0 / BSD-3-Clause | taking the app screenshots (`scripts/app_screenshots.py`) |
| Mozilla Firefox (headless) | MPL-2.0 | rendering the concept illustration (SVG → PNG) |
| ImageMagick 7.1.2 | ImageMagick licence (Apache-2.0-style) | cropping images |
| ElevenLabs: text to speech, music and sound effects | the team's ElevenLabs subscription terms; check that the plan covers commercial use before reusing the audio | voiceover, background music and the click sound of the pitch video (`scripts/video/`). The other sound effects (whooshes, pops, hits) are synthesised by our own code |
| FFmpeg (static build from imageio-ffmpeg, with libx264) | GPL-3.0 for this build; the licence covers the tool, not the video it encodes | mixing the audio and encoding the video |
| Vega 6, Vega-Lite 6.4, vega-embed 7 (loaded from jsDelivr) | BSD-3-Clause | the opening chart of the video |
| faster-whisper 1.2 with the Whisper small.en model | MIT (both) | when each word is spoken in the voice clips, so captions, text and camera moves land on the word; not part of the video |
| Poppins font files (Google Fonts GitHub) | SIL Open Font License 1.1 | captions and the € counter drawn into the video frames |

## Models and AI services

| item | terms | how it was used |
|---|---|---|
| **Claude (Anthropic), via Claude Code** | Anthropic's commercial terms of service | AI coding and analysis assistant: wrote and ran analysis scripts, the app changes, the documents and the deck under the team's direction. Commits made with it carry a `Co-Authored-By: Claude` line. Not part of the delivered software |
| **ElevenLabs** (text to speech, music, sound effects) | the team's subscription terms | the voice, music and click sound of the pitch video are AI-generated; the script was written by the team with Claude |
| No machine-learning model is shipped. The only model is a scikit-learn gradient-boosting regressor trained at run time on the synthetic data, in the no-scale weight experiments | – | research only |

## External sources

Patent and vendor pages used as background for the weighing options in the concept. They were used for reasoning only; nothing was copied:
- [US11162834B2: weight-measurement retrofitting for waste compactors](https://patents.google.com/patent/US11162834)
- [US12379240B1: container weighing with load cells](https://patents.google.com/patent/US12379240)
- [Vulcan on-board scale for roll-offs (Trailer/Body Builders)](https://www.trailer-bodybuilders.com/archive/article/21723735/vulcan-offers-on-board-scale-for-roll-offs)
- [On-board scale built for roll-offs (Recycling Product News)](https://www.recyclingproductnews.com/article/8417/on-board-scale-built-for-roll-offs)
- [Anderson-Negele Microcell bolt-on sensor, data sheet](https://www.anderson-negele.com/uk/wp-content/uploads/sites/11/2021/04/Microcell_L-Cell_at_a_glance_60034_1.0_en_eu.pdf)
- [Applied Measurements bolt-on sensors (DirectIndustry)](https://directindustry.com/prod/applied-measurements/product-11673-862661.html)
- [Bolt-on force sensors for retrofit weighing (automation.com)](https://www.automation.com/article/bolt-on-force-sensors-for-reliable-retrofit-weighi)

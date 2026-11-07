# Third-party libraries, data, models and services

The brief asks us to identify every third-party library, model, dataset or service we used, its licence and any commercial-use restrictions. Versions are the ones installed in the development environment, read from each package's own metadata. *This is a list, not legal advice.*

## Dataset

| item | licence / terms | commercial-use notes |
|---|---|---|
| Europress × Since AI Hackathon 2026 synthetic dataset and generator, v1.0.1 (`data/`, `src/europress_data/`, `baselines/`, `docs/`, `examples/`, `tests/`) | no separate licence file; the README says use of the data and of team results follows the **Since AI Hackathon 2026 rules** | entirely synthetic, no personal data; prices are hypothetical. Check the event rules before any use outside the hackathon |

Our own work on top of it: `app/`, `notes/`, `configs/our_params.yaml`, `our_business_case/`, `submission/`.

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
| matplotlib | 3.11.2 | Matplotlib licence (PSF-based, BSD-compatible) | analysis charts in `notes/` |
| scikit-learn | 1.9.1 | BSD-3-Clause | gradient boosting in the no-scale weight experiments |
| pytest | 9.2.0 | MIT | the dataset package's tests |
| Markdown | 3.11.3 | BSD-3-Clause | docs build of the dataset package |

All of these are permissive licences that allow commercial use. Apache-2.0 asks you to keep its NOTICE and licence text when redistributing; BSD and MIT ask you to keep the copyright notice.

## Tools used only to produce submission files (not needed to run the demo)

| tool | licence | used for |
|---|---|---|
| PptxGenJS 3.12.0 (Node.js) | MIT | building `submission/pitch_deck.pptx` (`submission/deck_src/build_deck.js`) |
| react-icons 5.4.0 · React / ReactDOM 18.3.1 · sharp 0.33.5 | MIT (icons: Font Awesome Free icons, CC BY 4.0) · MIT · Apache-2.0 | the three icons on slide 3 |
| LibreOffice | MPL-2.0 | exporting the deck to PDF |
| Playwright 1.64.1 (Python) with Chromium headless shell | Apache-2.0 / BSD-3-Clause | taking the app screenshots in `notes/screenshots/` |
| Mozilla Firefox (headless) | MPL-2.0 | rendering the concept illustration (SVG → PNG) |
| ImageMagick 7.1.2 | ImageMagick licence (Apache-2.0-style) | cropping images |

## Models and AI services

| item | terms | how it was used |
|---|---|---|
| **Claude (Anthropic), via Claude Code** | Anthropic's commercial terms of service | AI coding and analysis assistant: wrote and ran analysis scripts, the app changes, the documents and the deck under the team's direction. Commits made with it carry a `Co-Authored-By: Claude` line. Not part of the delivered software |
| No machine-learning model is shipped. The only model is a scikit-learn gradient-boosting regressor trained at run time on the synthetic data (`notes/weight_without_scale.py`) | – | research only |

## External sources (research, U11)

Patent and vendor pages are cited in `notes/FINDINGS.md` (U11) and were used for reasoning only; nothing was copied:
- US11162834B2;
- US12379240B1;
- Trailer/Body Builders and Recycling Product News articles on on-board roll-off scales;
- Anderson-Negele and Applied Measurements bolt-on sensor sheets;
- an automation.com article on bolt-on force sensors.

"""Compile releases/HANDOVER_REPORT.md from actual outputs. python scripts/handover_report.py"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R, REL = ROOT / "reports", ROOT / "releases"


def load(p):
    p = Path(p)
    return json.load(open(p)) if p.exists() else None


L = ["# Handover report — Europress SMART Material Value Engine synthetic data (v1.0.0rc1)", "",
     "**Status: SYNTHETIC — pending Since AI and Europress release approval. Not approved.**", ""]
ver = load(REL / "release_verification.json") or []
L += ["## Deliverables", "", "| file | size | files | integrity | public-leak check | example queries |", "|---|---|---|---|---|---|"]
for v in ver:
    L.append(f"| `{v['zip']}` | {v['bytes'] / 1e6:.1f} MB | {v['n_files']} | testzip {'OK' if v['testzip_ok'] else 'FAIL'}"
             f"{'; manifest mismatches ' + str(v.get('manifest_checksum_mismatches')) if 'manifest_checksum_mismatches' in v else ''} | "
             f"{('forbidden paths: ' + str(len(v['forbidden_paths']))) if 'forbidden_paths' in v else 'n/a (private)'} | {v.get('example_queries', '—')} |")
L += ["", "SHA-256: see `release_verification.json`.", ""]
L += ["## Generated profiles", "", "| profile | devices (public + hold-out) | days | telemetry messages (public) | runtime | public MB | private MB | validation |", "|---|---|---|---|---|---|---|---|"]
for prof in ("quickstart", "competition", "enterprise"):
    g = load(ROOT / "data" / prof / "generation_summary.json")
    v = load(R / prof / "validation_report.json")
    m = load(ROOT / "data" / prof / "public" / "metadata" / "dataset_manifest.json")
    if not g:
        continue
    tel = sum(f.get("rows", 0) for f in m["files"] if "telemetry_hourly/" in f["path"]) if m else None
    val = f"{v['n_checks']} checks, {v['blocking_failures']} blocking, {v['warnings']} warnings" if v else "not run"
    L.append(f"| {prof} | {g['n_devices_public']} + {g['n_devices_holdout']} | {g['n_days']} | {tel:,} | {g['runtime_seconds']} s | {g['bytes_public'] / 1e6:.0f} | {g['bytes_private'] / 1e6:.0f} | {val} |")
L += [""]
pt = R / "pytest.txt"
if pt.exists():
    L += ["## Tests", "", "```", pt.read_text().strip().splitlines()[-1], "```", ""]
b = load(R / "baselines_competition.json")
if b:
    L += ["## Baselines (competition)", "",
          f"* Task A (B1): net contribution exact to the cent — validation {b['task_A']['B1_calculator']['validation']['net_material_contribution_eur:exact_to_cent_share']}, test {b['task_A']['B1_calculator']['test']['net_material_contribution_eur:exact_to_cent_share']}; fabricated €/t: {b['task_A']['B1_calculator']['test']['per_t:fabricated_where_reference_null']}",
          "* Task B macro-F1 (validation / test): " + "; ".join(f"{k} {v['validation']['macro_f1']} / {v['test']['macro_f1']}" for k, v in b["task_B"].items()),
          "* Task C mean regret € (validation / test): " + "; ".join(f"{k} {v['validation']['mean_regret_eur']} / {v['test']['mean_regret_eur']}" for k, v in b["task_C"].items()), ""]
L += ["## What was NOT done / limitations", "",
      "* No calibration against real Europress, operator or market data (by design: none was provided or used).",
      "* Enterprise profile generated and validated as a scale test; it is not packaged as a ZIP (size) — regenerate with the CLI.",
      "* Task D/E are judged with a rubric; there is no automatic score for business reasoning.",
      "* Service pricing and adoption are not in the dataset; teams set and justify them as parameters (Task D).",
      "* See docs/ASSUMPTIONS_AND_LIMITATIONS.md for the full list.", ""]
(REL / "HANDOVER_REPORT.md").write_text("\n".join(L))
print("\n".join(L))

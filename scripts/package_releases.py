"""Build and verify the release ZIPs.  python scripts/package_releases.py

1. Europress_SMART_Material_Value_Engine_v<ver>_PARTICIPANTS.zip  - the ONE shareable package (code, docs, both
   public data packs). Contains no private evaluation data, no organiser seeds, no test-period scores.
2. Europress_SMART_Material_Value_Engine_v<ver>_ORGANIZERS_PRIVATE_DO_NOT_SHARE.zip - private evaluation data,
   organiser-held seeds, full baseline results incl. test, validation reports, business-case example output.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from europress_data import GENERATOR_VERSION  # noqa: E402

REL = ROOT / "releases"
V = GENERATOR_VERSION
TOP = f"Europress_SMART_Material_Value_Engine_v{V}"
CODE = ["START_HERE.md", "START_HERE.html", "README.md", "pyproject.toml", "configs", "src", "baselines", "examples", "docs", "scripts", "tests"]
FORBIDDEN_IN_PUBLIC = ("private_evaluation", "/truth/", "labels_test", "holdout_full", "holdout_asof", "golden_cases_private",
                       "seeds.json", "organizer", "BASELINE_RESULTS_INCL_TEST", "business_case_customers", "business_case_scenarios")
SKIP = ("__pycache__", ".pytest_cache", ".egg-info")
ABS_PATH_RE = "|".join(re.escape(p) for p in (str(ROOT.parent), "/tmp/" + "claude"))   # generation-environment paths


def add_tree(z: zipfile.ZipFile, src: Path, arc: str):
    if src.is_file():
        z.write(src, arc, compress_type=zipfile.ZIP_STORED if src.suffix == ".parquet" else zipfile.ZIP_DEFLATED)
        return
    for p in sorted(src.rglob("*")):
        if p.is_file() and not any(s in str(p) for s in SKIP):
            z.write(p, f"{arc}/{p.relative_to(src)}", compress_type=zipfile.ZIP_STORED if p.suffix == ".parquet" else zipfile.ZIP_DEFLATED)


def build(name: str, parts: list) -> Path:
    REL.mkdir(exist_ok=True)
    out = REL / name
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w") as z:
        for src, arc in parts:
            if not src.exists():
                raise FileNotFoundError(src)
            add_tree(z, src, arc)
    return out


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def secret_seeds() -> list:
    return [str(v) for v in json.load(open(ROOT / "organizer" / "seeds.json")).values()]


def verify(zp: Path, public: bool, data_prefixes: list) -> dict:
    res = {"zip": zp.name, "bytes": zp.stat().st_size, "sha256": sha(zp)}
    with zipfile.ZipFile(zp) as z:
        res["testzip_ok"] = z.testzip() is None
        names = z.namelist()
        res["n_files"] = len(names)
        if public:
            res["forbidden_paths"] = [n for n in names if any(f in n for f in FORBIDDEN_IN_PUBLIC)]
            seeds = secret_seeds()
            leaks = []
            for n in names:
                if n.endswith((".json", ".md", ".txt", ".yaml", ".py", ".csv", ".html", ".sh")):
                    t = z.read(n).decode("utf-8", "ignore")
                    if any(s in t for s in seeds):
                        leaks.append(n)
                    if re.search(ABS_PATH_RE, t):
                        leaks.append(n + " (absolute path)")
            res["secret_seed_or_path_leaks"] = leaks
        with tempfile.TemporaryDirectory() as td:
            z.extractall(td)
            for pre in data_prefixes:
                root = Path(td) / pre
                man = json.load(open(root / "metadata" / "dataset_manifest.json"))
                bad = [f["path"] for f in man["files"] if not (root / f["path"]).exists() or sha(root / f["path"]) != f["sha256"]]
                res[f"{pre}:manifest_files"] = man["n_files"]
                res[f"{pre}:checksum_mismatches"] = len(bad)
                if public:
                    res[f"{pre}:seed_field"] = man["seed"]
                    repo = Path(td) / TOP
                    r = subprocess.run([sys.executable, "-I", str(repo / "examples" / "run_queries.py"), str(root)], capture_output=True, text=True,
                                       cwd=td, env={"PYTHONPATH": str(repo / "src"), "PATH": "/usr/bin:/bin"})
                    res[f"{pre}:example_queries"] = (r.stdout.strip().splitlines() or ["(no output)"])[-1] if r.returncode == 0 else f"FAILED: {r.stderr[-300:]}"
    return res


def main():
    for old in REL.glob("*.zip"):
        old.unlink()
    code = [(ROOT / c, f"{TOP}/{c}") for c in CODE]
    data = [(ROOT / f"data/{p}/public", f"{TOP}/data/{p}/public") for p in ("quickstart", "competition")]
    part = build(f"{TOP}_PARTICIPANTS.zip", code + data)
    built = [verify(part, True, [f"{TOP}/data/quickstart/public", f"{TOP}/data/competition/public"])]
    priv_parts = [(ROOT / "data/competition/private_evaluation", f"{TOP}_PRIVATE/competition/private_evaluation"),
                  (ROOT / "data/quickstart/private_evaluation", f"{TOP}_PRIVATE/quickstart/private_evaluation"),
                  (ROOT / "organizer", f"{TOP}_PRIVATE/organizer"),
                  (ROOT / "reports", f"{TOP}_PRIVATE/reports")]
    priv = build(f"{TOP}_ORGANIZERS_PRIVATE_DO_NOT_SHARE.zip", priv_parts)
    built.append(verify(priv, False, [f"{TOP}_PRIVATE/competition/private_evaluation"]))
    json.dump(built, open(REL / "release_verification.json", "w"), indent=2)
    print(json.dumps(built, indent=2))
    pub = built[0]
    ok = (not pub["forbidden_paths"] and not pub["secret_seed_or_path_leaks"] and pub["testzip_ok"]
          and all(v == 0 for k, v in pub.items() if k.endswith("checksum_mismatches")))
    print("PUBLIC PACKAGE CHECKS:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
